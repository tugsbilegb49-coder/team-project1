"""Presence-only capture: frames stay in RAM; only scalar results leave the loop."""
import csv
from datetime import datetime, timedelta
import io
import json
import math
import os
from pathlib import Path
import tempfile
import time
from zoneinfo import ZoneInfo


def validate_presence(present, confidence):
    if not isinstance(present, bool):
        raise ValueError('present must be a boolean.')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError('confidence must be finite and between 0 and 1.')


class PresenceLogger:
    fields = ('timestamp', 'present', 'confidence')

    def __init__(self, path, max_bytes=5 * 1024 * 1024, backup_count=3, retention_days=7, clock=None):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 256:
            raise ValueError('Presence log max_bytes must be at least 256.')
        if isinstance(backup_count, bool) or not isinstance(backup_count, int) or not 0 <= backup_count <= 100:
            raise ValueError('Presence log backup_count must be between 0 and 100.')
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
            raise ValueError('Presence log retention_days must be positive.')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.backup_count, self.retention_days = max_bytes, backup_count, retention_days
        self.clock = clock or (lambda: datetime.now(ZoneInfo('Asia/Ulaanbaatar')))
        self.header = self._csv_line(self.fields)
        self.stream = None
        self.day = None
        self._prune()
        for path in (self.path, *(self._backup(i) for i in range(1, self.backup_count + 1))):
            self._trim_oversized(path)
        if self.path.exists() and self.path.stat().st_size:
            self.day = datetime.fromtimestamp(self.path.stat().st_mtime, ZoneInfo('Asia/Ulaanbaatar')).date()
        self._open()

    @staticmethod
    def _csv_line(values):
        buffer = io.StringIO(newline='')
        csv.writer(buffer, lineterminator='\n').writerow(values)
        return buffer.getvalue()

    def _backup(self, number):
        return self.path.with_name(self.path.name+'.'+str(number))

    def _prune(self):
        cutoff = (self.clock() - timedelta(days=self.retention_days)).timestamp()
        candidates = [(self.path, 0)]
        for path in self.path.parent.glob(self.path.name+'.*'):
            suffix = path.name[len(self.path.name)+1:]
            # Only the numbered files this logger creates, never manual archives.
            if suffix.isdecimal() and str(int(suffix)) == suffix and 1 <= int(suffix) <= 100:
                candidates.append((path, int(suffix)))
        for path, number in candidates:
            if path.exists() and (number > self.backup_count or path.stat().st_mtime < cutoff):
                path.unlink()

    def _trim_oversized(self, path):
        if not path.exists() or path.stat().st_size <= self.max_bytes:
            return
        original = path.stat()
        header = self.header.encode('utf-8')
        with path.open('rb') as stream:
            if stream.readline().rstrip(b'\r\n') != header.rstrip(b'\n'):
                raise ValueError('Existing presence CSV has an unexpected header; use a different log path.')
            stream.seek(-self.max_bytes, os.SEEK_END)
            stream.readline()  # Discard a possibly partial oldest row.
            tail = stream.read()
        while len(header) + len(tail) > self.max_bytes:
            tail = tail.partition(b'\n')[2]
        fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(header + tail)
                stream.flush()
                os.fsync(stream.fileno())
            os.utime(temporary, ns=(original.st_atime_ns, original.st_mtime_ns))
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _open(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.stream = os.fdopen(fd, 'a', newline='', encoding='utf-8')
        if self.path.stat().st_size == 0:
            self.stream.write(self.header)
            self.stream.flush()
        if self.day is None:
            self.day = self.clock().date()

    def _rotate(self):
        self.stream.close()
        if self.backup_count:
            self._backup(self.backup_count).unlink(missing_ok=True)
            for number in range(self.backup_count - 1, 0, -1):
                if self._backup(number).exists():
                    os.replace(self._backup(number), self._backup(number + 1))
            os.replace(self.path, self._backup(1))
        else:
            self.path.unlink(missing_ok=True)
        self._prune()
        self.day = self.clock().date()
        self._open()

    def log(self, present, confidence, timestamp=None):
        validate_presence(present, confidence)
        row = self._csv_line(((timestamp or self.clock()).isoformat(), int(present), round(confidence, 6)))
        if self.day != self.clock().date() or self.path.stat().st_size + len(row.encode('utf-8')) > self.max_bytes:
            self._rotate()
        self.stream.write(row)
        self.stream.flush()

    def close(self):
        if self.stream:
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
        import numpy as np
        from src.detector import ObjectDetector
        from src.api_logger import PresenceEventUploader, CameraAPISyncError
        detector, cap = None, None
        logger, uploader = None, None
        guard = None
        paused_frame = np.zeros((160, 640, 3), dtype=np.uint8)
        try:
            logger = PresenceLogger(self.config.get('presence_log_file', 'data/presence.csv'),
                max_bytes=self.config.get('presence_log_max_bytes', 5 * 1024 * 1024),
                backup_count=self.config.get('presence_log_backups', 3),
                retention_days=self.config.get('presence_log_retention_days', 7))
            sync = self.config.get('api_sync', {})
            if sync.get('enabled'):
                uploader = PresenceEventUploader(sync.get('api_url', 'http://127.0.0.1:8000'),
                    sync.get('token_file', 'agent/.agent_tokens.json'),
                    sync.get('device_config_file', 'agent/config.json'),
                    self.config.get('presence_queue_file', 'data/.pending_presence_events.json'),
                    sync.get('max_queue_events', 10000), sync.get('max_queue_bytes', 10485760))
                guard = uploader.consent_guard
                guard.start()
            start = time.monotonic()
            next_sample = start
            print('Presence demo: q = stop. Frames/video are never saved. Pause uses agent/control.json.')
            result = None
            while seconds is None or time.monotonic() - start < seconds:
                # Process quit in every state, including before authorization.
                if cv2.waitKey(1) & 0xff == ord('q'):
                    break
                if self.paused() or (guard is not None and not guard.allowed()):
                    if cap is not None:
                        cap.release()
                        cap = None
                    result = None
                    placeholder = paused_frame.copy()
                    cv2.putText(placeholder, 'Camera paused / consent pending. q = stop',
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
                    cv2.imshow('WorkTrack presence (no recording)', placeholder)
                    time.sleep(.05)
                    continue
                if detector is None:
                    detector = ObjectDetector(self.config['model_name'], self.config['confidence_threshold'])
                # Model loading can take time; recheck before opening hardware.
                if self.paused() or (guard is not None and not guard.allowed()):
                    continue
                if cap is None:
                    cap = cv2.VideoCapture(self.config['camera_index'])
                    if not cap.isOpened():
                        raise RuntimeError('Could not open webcam. Check camera permission and camera_index.')
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Camera frame could not be read.')
                now = time.monotonic()
                if now >= next_sample:
                    result = detector.detect_presence(frame, self.config.get('labels', {}).get('person', 'person'))
                    if not self.paused() and (guard is None or guard.allowed()):
                        timestamp = datetime.now().astimezone()
                        logger.log(**result, timestamp=timestamp)
                        if uploader:
                            try:
                                uploader.log(**result, timestamp=timestamp)
                            except CameraAPISyncError as exc:
                                print(f'Presence upload queued locally: {exc}')
                    next_sample = now + self.interval
                if self.paused() or (guard is not None and not guard.allowed()):
                    continue
                if result:
                    text = f"Person {'present' if result['present'] else 'absent'}  confidence={result['confidence']:.2f}"
                    cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 0), 2)
                cv2.imshow('WorkTrack presence (no recording)', frame)
        finally:
            if cap is not None:
                cap.release()
            cv2.destroyAllWindows()
            if uploader:
                uploader.close()
            if logger:
                logger.close()
