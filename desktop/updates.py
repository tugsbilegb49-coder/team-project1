"""Tell the employee when the admin has published a newer WorkTrack app.

The admin enters the newest version and its download link in «Monitoring тохиргоо»; the server's
/api/health/ passes them on. This only informs: the employee downloads and installs the new app
themselves (it replaces the old folder; data in the user profile stays).
"""

import json
import threading

from agent.token_store import atomic_json_write
from agent.version import VERSION, is_newer

FIRST_CHECK_AFTER = 30
CHECK_EVERY = 6 * 60 * 60


def message(version):
    return f'WorkTrack-ийн шинэ хувилбар {version} гарлаа. WorkTrack-ийн хуудаснаас татаж суулгана уу.'


class UpdateCheck:
    def __init__(self, controller, autostart=True, fetch=None, send=None):
        from desktop.reminders import notify

        self.controller = controller
        self.fetch = fetch or self._fetch
        self.send = send or notify
        self.available = None
        self.noticed = controller.runtime / 'update-notice.json'
        self.stopping = threading.Event()
        self.thread = None
        if autostart:
            self.thread = threading.Thread(target=self._run, name='update-check', daemon=True)
            self.thread.start()

    def _fetch(self):
        from urllib.request import Request

        from agent.transport import open_url

        with open_url(Request(self.controller.api + '/api/health/'), timeout=8) as response:
            return json.load(response)

    def check(self):
        """Read the server's latest version; returns the update on offer, or None."""
        try:
            client = self.fetch().get('client') or {}
            version, link = str(client.get('version', '')), str(client.get('download_url', ''))
        except (OSError, ValueError, AttributeError):
            return self.available  # Offline: keep what was known.
        if not is_newer(version, VERSION) or not link.lower().startswith(('https://', 'http://')):
            self.available = None
            return None
        self.available = {'version': version, 'download_url': link}
        try:
            told = json.loads(self.noticed.read_text(encoding='utf-8')).get('version')
        except (OSError, ValueError, AttributeError):
            told = None
        if told != version:  # One system notification per new version; the page keeps showing it.
            self.send(message(version))
            atomic_json_write(self.noticed, {'version': version})
        return self.available

    def _run(self):
        if self.stopping.wait(FIRST_CHECK_AFTER):
            return
        while True:
            self.check()
            if self.stopping.wait(CHECK_EVERY):
                return

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=3)
