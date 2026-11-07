"""
monitor.py
----------
Wires together the webcam feed, object detector, optional gaze heuristic,
activity state machine, and CSV logger into a runnable monitoring session.
"""

import cv2
import json
from datetime import datetime
from pathlib import Path
import yaml

from src.detector import ObjectDetector
from src.activity_tracker import ActivityTracker, classify
from src.logger import CSVActivityLogger, print_summary
from src.api_logger import CameraAPISyncError, CameraEventUploader


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class WorkerActivityMonitor:
    def __init__(self, config: dict):
        self.config = config
        self.session = None

        self.detector = ObjectDetector(
            model_name=config["model_name"],
            confidence_threshold=config["confidence_threshold"],
        )

        self.gaze = None
        if config.get("use_gaze_heuristic"):
            from src.gaze import GazeEstimator  # lazy import (optional dep)
            self.gaze = GazeEstimator()

        self.logger = CSVActivityLogger(config["log_file"], multi_person=False)
        sync_config = config.get("api_sync", {})
        self.api_uploader = None
        if sync_config.get("enabled"):
            self.api_uploader = CameraEventUploader(
                api_url=sync_config.get("api_url", "http://127.0.0.1:8000"),
                token_file=sync_config.get("token_file", "agent/.agent_tokens.json"),
                device_config_file=sync_config.get("device_config_file", "agent/config.json"),
                queue_file=sync_config.get("queue_file", "data/.pending_camera_events.json"),
                max_queue_events=sync_config.get("max_queue_events", 10000),
                max_queue_bytes=sync_config.get("max_queue_bytes", 10485760),
            )
        self.tracker = ActivityTracker(on_segment=self._on_transition, max_gap_seconds=config.get("max_camera_gap_seconds", 10))

        self.labels = config["labels"]
        self.detect_every_n = config.get("detect_every_n_frames", 5)
        self.frame_count = 0
        self.control_file = Path(config.get("control_file", "agent/control.json"))

    def _is_paused(self) -> bool:
        from src.camera_session import locally_paused
        return locally_paused(self.config) or (self.api_uploader is not None and not self.api_uploader.consent_guard.allowed())

    def _on_transition(self, old_state: str, duration: float, ended_at: float) -> None:
        if self._is_paused():
            return
        timestamp = datetime.fromtimestamp(ended_at).astimezone()
        self.logger.log(old_state, duration, timestamp=timestamp)
        if self.api_uploader is not None:
            try:
                self.api_uploader.log(old_state, duration, timestamp=timestamp)
            except CameraAPISyncError as exc:
                # Do not discard the local CSV record if the API is unavailable.
                print(f"Camera API sync skipped: {exc}")

    def _classify_frame(self, frame) -> str:
        detected = self.detector.detect_labels(frame)

        looking_at_phone = None
        if self.gaze is not None and self.labels["phone"] in detected:
            looking_at_phone = self.gaze.is_looking_down(frame)

        return classify(
            detected,
            person_label=self.labels["person"],
            laptop_label=self.labels["laptop"],
            phone_label=self.labels["phone"],
            looking_at_phone=looking_at_phone,
        )

    def _apply_settings(self, settings):
        self.detector.confidence_threshold=settings['camera_threshold']
        self.logger.configure(settings)

    def run(self, seconds=None) -> None:
        from src.camera_session import CameraSession
        print("Monitoring started. Press 'q' in the video window to stop.")
        guard = self.api_uploader.consent_guard if self.api_uploader else None
        if guard: guard.start()
        self.session = CameraSession(self.config, guard, seconds, self.tracker.reset_timer,
                                     self.api_uploader,self._apply_settings)
        try:
            for frame in self.session.frames():
                self.frame_count += 1
                if self.frame_count % self.detect_every_n == 0:
                    state = self._classify_frame(frame)
                    if self.session.allowed():
                        self.tracker.update(state)
                if not self.session.allowed(): continue
                self._draw_overlay(frame)
                cv2.imshow("Worker Activity Monitor", frame)
        finally:
            self.tracker.finalize()
            self.session.close()
            if self.api_uploader is not None:
                self.api_uploader.close()
            self.logger.close()
            if self.gaze is not None:
                self.gaze.close()
            print_summary(self.config["log_file"])

    def _draw_overlay(self, frame) -> None:
        elapsed = self.tracker.current_elapsed()
        text = "Monitoring paused" if self._is_paused() else f"State: {self.tracker.state}  ({elapsed:.0f}s)"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 0), 2)
