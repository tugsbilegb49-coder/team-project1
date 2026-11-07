"""Upload durable launcher intervals for the verified, consenting device owner."""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone

from agent.main import ApiClient, ApiError, AgentError, AccountChangedError


def usage_scope(api, user_id):
    return hashlib.sha256((api.rstrip('/')+'\0'+str(user_id)).encode()).hexdigest()


class UsageSync:
    def __init__(self, controller, autostart=True):
        self.controller = controller
        self.stopping = threading.Event()
        self.thread = None
        self.last_upload = None
        self.error = ''
        if autostart:
            self.thread = threading.Thread(target=self._run, name='launcher-usage-upload', daemon=True)
            self.thread.start()

    def cycle(self):
        controller = self.controller
        # Serialize linking/disconnecting with validation and upload. The ApiClient
        # also refuses a token-file account change between requests.
        with controller.lock:
            if controller.closed:
                return
            if not controller.owner:
                controller.usage.bind()
                self.error = 'unlinked'
                return
            try:
                client = ApiClient(controller.api, controller.tokens)
                user = client.get('/api/users/me/')
                config = json.loads(controller.config.read_text())
                if user['id'] != controller.owner['user_id'] or config.get('api_url', '').rstrip('/') != controller.api.rstrip('/'):
                    raise AccountChangedError('Owner changed')
                scope = usage_scope(controller.api, user['id'])
                # Empty batches validate consent + enabled device even without new time.
                client._authenticated_post('/api/launcher-usage/', {'device_id': config['device_id'], 'intervals': []})
                controller.usage.bind(scope, config['device_id'])
                rows = controller.usage.pending(scope, str(config['device_id']))
                by_device = {}
                for row in rows:
                    by_device.setdefault(row['device_id'], []).append(row)
                for device, batch in by_device.items():
                    payload = [{'event_id': row['event_id'],
                                'started_at': datetime.fromtimestamp(row['started_at'], timezone.utc).isoformat(),
                                'ended_at': datetime.fromtimestamp(row['ended_at'], timezone.utc).isoformat()} for row in batch]
                    client._authenticated_post('/api/launcher-usage/', {'device_id': device, 'intervals': payload})
                    controller.usage.acknowledge(batch)
                self.last_upload = datetime.now(timezone.utc).isoformat()
                self.error = ''
            except (ApiError, AccountChangedError) as exc:
                if isinstance(exc, AccountChangedError) or getattr(exc, 'status', 0) in (401, 403):
                    controller.usage.bind()
                self.error = 'permission' if getattr(exc, 'status', 0) == 403 else 'connection'
            except (AgentError, OSError, sqlite3.Error, ValueError, KeyError, TypeError):
                # Keep a verified binding during a network outage; the pending
                # rows stay on disk and can only be uploaded as that same owner.
                self.error = 'connection'

    def _run(self):
        while not self.stopping.is_set():
            self.cycle()
            self.stopping.wait(30)

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=3)
