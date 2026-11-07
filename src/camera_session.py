"""Shared timed/consented camera loop for optional activity experiments."""

import json
from pathlib import Path
import time


def locally_paused(config):
    try:
        return bool(json.loads(Path(config.get('control_file', 'agent/control.json')).read_text()).get('paused', False))
    except FileNotFoundError:
        return False
    except (OSError, ValueError, AttributeError):
        return True


class CameraSession:
    def __init__(self, config, guard=None, seconds=None, reset=None, uploader=None, configure=None):
        self.config, self.guard, self.seconds, self.reset = config, guard, seconds, reset
        self.cap = None
        self.runtime = None
        self.configure = configure
        self.applied_version = None
        if uploader is not None:
            device_id = uploader._device_id()
            if isinstance(device_id, str) and device_id:
                from agent.main import ApiClient
                from agent.runtime import AgentRuntime

                self.runtime = AgentRuntime(
                    ApiClient(uploader.api_url, uploader.token_file),
                    device_id,
                    uploader._worker,
                    lambda: not self.allowed(),
                    kind='camera',
                )

    def allowed(self):
        from src.camera_capture import check_session

        check_session()
        return not locally_paused(self.config) and (self.guard is None or self.guard.allowed())

    def frames(self):
        import cv2
        import numpy as np

        start = time.monotonic()
        if self.runtime:
            self.runtime.start()
        was_paused = True
        while self.seconds is None or time.monotonic() - start < self.seconds:
            from src.camera_capture import check_session

            check_session()
            data = self.runtime.snapshot() if self.runtime else {}
            if data.get('version') is not None and data['version'] != self.applied_version:
                if self.configure:
                    self.configure(data)
                self.applied_version = data['version']
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if not self.allowed():
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                if self.reset:
                    self.reset()
                was_paused = True
                blank = np.zeros((160, 640, 3), dtype=np.uint8)
                cv2.putText(
                    blank,
                    'Camera paused / consent pending. q = stop',
                    (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    1,
                )
                cv2.imshow('Worker Activity Monitor', blank)
                time.sleep(0.05)
                continue
            if was_paused and self.reset:
                self.reset()
            was_paused = False
            if self.cap is None:
                from src.camera_capture import open_camera

                self.cap = open_camera(self.config['camera_index'], permitted=self.allowed)
                if self.cap is None:
                    continue
                if not self.cap.isOpened():
                    raise RuntimeError('Could not open webcam. Check OS permission and camera_index.')
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError('Could not read camera frame.')
            yield frame

    def close(self):
        import cv2

        if self.runtime:
            self.runtime.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()
