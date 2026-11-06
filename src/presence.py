"""Presence-only capture: frames stay in RAM; only scalar results leave the loop."""
import csv
from datetime import datetime
import json
import math
import os
from pathlib import Path
import time


def validate_presence(present, confidence):
    if not isinstance(present, bool):
        raise ValueError('present must be a boolean.')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('confidence must be finite and between 0 and 1.')


class PresenceLogger:
    fields = ('timestamp', 'present', 'confidence')

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.stream = os.fdopen(fd, 'a', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.stream, fieldnames=self.fields)
        if self.path.stat().st_size == 0:
            self.writer.writeheader()

    def log(self, present, confidence, timestamp=None):
        validate_presence(present, confidence)
        self.writer.writerow({'timestamp': (timestamp or datetime.now().astimezone()).isoformat(),
                              'present': int(present), 'confidence': round(confidence, 6)})
        self.stream.flush()

    def close(self):
        self.stream.close()


class PresenceMonitor:
    def __init__(self, config):
        self.config = config
        interval = config.get('presence_interval_seconds', 1)
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError('presence_interval_seconds must be positive.')
        self.interval = interval
        self.control = Path(config.get('control_file', 'agent/control.json'))

    def paused(self):
        try:
            return bool(json.loads(self.control.read_text(encoding='utf-8')).get('paused', False))
        except FileNotFoundError:
            return False
        except (OSError, ValueError, AttributeError):
            return True

    def run(self, seconds=None):
        import cv2
        from src.detector import ObjectDetector
        from src.api_logger import PresenceEventUploader, CameraAPISyncError
        detector = ObjectDetector(self.config['model_name'], self.config['confidence_threshold'])
        cap = cv2.VideoCapture(self.config['camera_index'])
        logger, uploader = None, None
        try:
            if not cap.isOpened():
                raise RuntimeError('Could not open webcam. Check camera permission and camera_index.')
            logger = PresenceLogger(self.config.get('presence_log_file', 'data/presence.csv'))
            sync = self.config.get('api_sync', {})
            if sync.get('enabled'):
                uploader = PresenceEventUploader(sync.get('api_url', 'http://127.0.0.1:8000'),
                    sync.get('token_file', 'agent/.agent_tokens.json'),
                    sync.get('device_config_file', 'agent/config.json'),
                    self.config.get('presence_queue_file', 'data/.pending_presence_events.json'),
                    sync.get('max_queue_events', 10000), sync.get('max_queue_bytes', 10485760))
            start = time.monotonic()
            next_sample = start
            print('Presence demo: q = stop. Frames/video are never saved. Pause uses agent/control.json.')
            result = None
            while seconds is None or time.monotonic() - start < seconds:
                if self.paused():
                    cv2.waitKey(50)
                    time.sleep(.05)
                    continue
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Camera frame could not be read.')
                now = time.monotonic()
                if now >= next_sample:
                    result = detector.detect_presence(frame, self.config.get('labels', {}).get('person', 'person'))
                    if not self.paused():
                        timestamp = datetime.now().astimezone()
                        logger.log(**result, timestamp=timestamp)
                        if uploader:
                            try:
                                uploader.log(**result, timestamp=timestamp)
                            except CameraAPISyncError as exc:
                                print(f'Presence upload queued locally: {exc}')
                    next_sample = now + self.interval
                if result:
                    text = f"Person {'present' if result['present'] else 'absent'}  confidence={result['confidence']:.2f}"
                    cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 0), 2)
                cv2.imshow('WorkTrack presence (no recording)', frame)
                if cv2.waitKey(1) & 0xff == ord('q'):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
            if uploader:
                uploader.close()
            if logger:
                logger.close()
