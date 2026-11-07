"""Operational heartbeat and settings polling, off the activity sampling thread."""

import threading


class AgentRuntime:
    def __init__(self, client, device_id, worker, paused, kind='computer', interval=30):
        self.client, self.device_id, self.worker, self.paused = client, device_id, worker, paused
        self.kind, self.interval = kind, interval
        self.lock = threading.Lock()
        self.settings = {}
        self.stopping = threading.Event()
        self.thread = None

    def snapshot(self):
        with self.lock:
            return dict(self.settings)

    def cycle(self):
        try:
            data = self.client.get('/api/monitoring-settings/')
            if isinstance(data, dict) and isinstance(data.get('version'), int):
                with self.lock:
                    self.settings = dict(data)
            with self.worker.lock:
                state = {
                    'queue_count': len(self.worker.pending),
                    'last_upload_at': self.worker.last_upload_at,
                    'error_code': self.worker.last_error,
                }
                if getattr(self.worker, 'unverified_count', 0):
                    state['error_code'] = 'legacy_queue'
            self.client._authenticated_post(
                '/api/agent-status/heartbeat/',
                {
                    'device_id': self.device_id,
                    'kind': self.kind,
                    'paused': bool(self.paused()),
                    'agent_version': '0.3.0',
                    'settings_version': self.snapshot().get('version', 0),
                    **state,
                },
            )
        except (OSError, RuntimeError, ValueError):
            # A failed heartbeat must not stop local sampling or erase configuration.
            return False
        return True

    def _run(self):
        while not self.stopping.is_set():
            self.cycle()
            self.stopping.wait(self.interval)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='agent-heartbeat', daemon=True)
            self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=3)
