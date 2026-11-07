"""
multi_monitor.py
-----------------
Multi-person version of the monitor: tracks each visible person with a
stable ID (via DeepSORT), associates the nearest laptop/phone detections to
each person, and maintains a separate ActivityTracker (state machine) per
person. This is what you want for an open-office/multi-desk camera feed
rather than a single dedicated workstation.
"""

import cv2
from datetime import datetime

from src.detector import ObjectDetector
from src.person_tracker import PersonTracker
from src.association import assign_objects_to_people, crop_box
from src.activity_tracker import ActivityTracker, classify
from src.logger import CSVActivityLogger, print_summary


class MultiPersonMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.session = None
        self.api_uploader = None
        sync = config.get('api_sync', {})
        if sync.get('enabled'):
            from src.api_logger import CameraEventUploader
            self.api_uploader = CameraEventUploader(sync.get('api_url','http://127.0.0.1:8000'),
                sync.get('token_file','agent/.agent_tokens.json'), sync.get('device_config_file','agent/config.json'),
                config.get('multi_control_queue_file','data/.pending_multi_control.json'))

        self.detector = ObjectDetector(
            model_name=config["model_name"],
            confidence_threshold=config["confidence_threshold"],
        )
        self.person_tracker = PersonTracker(max_age=config.get("track_max_age", 30))

        self.gaze = None
        if config.get("use_gaze_heuristic"):
            from src.gaze import GazeEstimator  # lazy import (optional dep)
            self.gaze = GazeEstimator()

        self.logger = CSVActivityLogger(config["log_file"], multi_person=True)
        self.trackers = {}  # track_id -> ActivityTracker

        self.labels = config["labels"]
        self.detect_every_n = config.get("detect_every_n_frames", 5)
        self.frame_count = 0

    def _get_tracker(self, track_id: int) -> ActivityTracker:
        if track_id not in self.trackers:
            self.trackers[track_id] = ActivityTracker(
                on_segment=lambda state, duration, end, tid=track_id: self._record_segment(state,duration,end,tid),
                max_gap_seconds=self.config.get("max_camera_gap_seconds", 10)
            )
        return self.trackers[track_id]

    def _record_segment(self, state, duration, end, track_id):
        from src.camera_session import locally_paused
        if locally_paused(self.config) or (self.api_uploader and not self.api_uploader.consent_guard.allowed()):
            return
        self.logger.log(state,duration,person_id=track_id,timestamp=datetime.fromtimestamp(end).astimezone())

    def _reset_timers(self):
        for tracker in self.trackers.values(): tracker.reset_timer()

    def _apply_settings(self, settings):
        self.detector.confidence_threshold=settings['camera_threshold']
        self.logger.configure(settings)

    def _process_frame(self, frame):
        detections = self.detector.detect_with_boxes(frame)

        person_dets = [d for d in detections if d["label"] == self.labels["person"]]
        laptop_boxes = [d["xyxy"] for d in detections if d["label"] == self.labels["laptop"]]
        phone_boxes = [d["xyxy"] for d in detections if d["label"] == self.labels["phone"]]

        tracked_people = self.person_tracker.update(frame, person_dets)  # {id: bbox}

        laptop_assignments = assign_objects_to_people(tracked_people, laptop_boxes)
        phone_assignments = assign_objects_to_people(tracked_people, phone_boxes)

        active_ids = set()
        for track_id, person_box in tracked_people.items():
            active_ids.add(track_id)
            has_laptop = len(laptop_assignments.get(track_id, [])) > 0
            has_phone = len(phone_assignments.get(track_id, [])) > 0

            looking_at_phone = None
            if self.gaze is not None and has_phone:
                crop = crop_box(frame, person_box)
                if crop is not None and crop.size > 0:
                    looking_at_phone = self.gaze.is_looking_down(crop)

            labels = {self.labels["person"]}
            if has_laptop:
                labels.add(self.labels["laptop"])
            if has_phone:
                labels.add(self.labels["phone"])

            state = classify(
                labels,
                person_label=self.labels["person"],
                laptop_label=self.labels["laptop"],
                phone_label=self.labels["phone"],
                looking_at_phone=looking_at_phone,
            )
            self._get_tracker(track_id).update(state)

        return tracked_people, active_ids

    def run(self, seconds=None):
        from src.camera_session import CameraSession
        print("Multi-person monitoring started. Press 'q' in the video window to stop.")
        tracked_people = {}
        guard = self.api_uploader.consent_guard if self.api_uploader else None
        if guard: guard.start()
        self.session = CameraSession(self.config,guard,seconds,self._reset_timers,self.api_uploader,self._apply_settings)
        try:
            for frame in self.session.frames():
                self.frame_count += 1
                if self.frame_count % self.detect_every_n == 0:
                    tracked_people, _ = self._process_frame(frame)
                if not self.session.allowed(): continue
                self._draw_overlay(frame, tracked_people)
                cv2.imshow("Worker Activity Monitor (multi-person)", frame)

        finally:
            for tracker in self.trackers.values():
                tracker.finalize()
            self.session.close()
            if self.api_uploader: self.api_uploader.close()
            self.logger.close()
            if self.gaze is not None:
                self.gaze.close()
            print_summary(self.config["log_file"])
            self._print_per_person_summary()

    def _draw_overlay(self, frame, tracked_people):
        for track_id, (x1, y1, x2, y2) in tracked_people.items():
            state = self.trackers[track_id].state if track_id in self.trackers else "?"
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {track_id}: {state}", (int(x1), int(y1) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def _print_per_person_summary(self):
        if not self.trackers:
            return
        print("\n--- Per-person summary ---")
        for track_id, tracker in self.trackers.items():
            print(f"Person {track_id}:")
            summary = tracker.summary()
            total = sum(summary.values())
            for state, secs in sorted(summary.items(), key=lambda x: -x[1]):
                pct = secs / total * 100 if total else 0
                print(f"  {state:10s}: {secs/60:6.1f} min ({pct:5.1f}%)")
