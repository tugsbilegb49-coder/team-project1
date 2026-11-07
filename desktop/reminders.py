"""Gentle reminders for a linked device: work not started, or still running late in the evening.

Only "seconds since the last keyboard/mouse input" is read, to tell whether someone is at the
computer. That number stays in memory: it is never stored or sent. Reminders can be turned off
from the web page and the choice is kept in .runtime/reminders.json.
"""

import base64
from datetime import datetime
import json
import shutil
import subprocess
import sys
import threading
import time

from agent.main import AgentError, idle_seconds, is_paused
from agent.token_store import atomic_json_write

WORK_HOURS = range(8, 19)  # A forgotten start is only worth a reminder during the working day...
WORK_DAYS = range(0, 5)  # ...Monday to Friday.
FORGOT_AFTER = 10 * 60  # Minutes of use without started work before the first reminder.
FORGOT_REPEAT = 2 * 60 * 60
ACTIVE_IDLE_LIMIT = 120  # Input within the last two minutes counts as "at the computer".
LATE_HOUR = 20
SHOW_FOR = 30 * 60  # How long the web page keeps showing the latest reminder.

FORGOT = 'Ажил эхлүүлэхээ мартсан уу? WorkTrack дээр «Ажил эхлүүлэх» дарна уу.'
LATE = 'Ажил асаалттай хэвээр байна. Дууссан бол WorkTrack дээр «Ажил дуусгах» дарна уу.'


def notify(message, title='WorkTrack'):
    """Best-effort OS notification; failures are ignored (the web page shows it too)."""
    try:
        if sys.platform == 'darwin':
            # Text goes in as an argument, never into the script source.
            script = ['-e', 'on run argv', '-e', 'display notification (item 1 of argv) with title (item 2 of argv)']
            subprocess.Popen(['/usr/bin/osascript', *script, '-e', 'end run', message, title])
        elif sys.platform == 'win32':
            quote = lambda text: "'" + text.replace("'", "''") + "'"  # noqa: E731
            script = (
                'Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; '
                '$n = New-Object System.Windows.Forms.NotifyIcon; '
                '$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; '
                f'$n.ShowBalloonTip(10000, {quote(title)}, {quote(message)}, "Info"); '
                'Start-Sleep -Seconds 12; $n.Dispose()'
            )
            encoded = base64.b64encode(script.encode('utf-16-le')).decode()
            subprocess.Popen(
                ['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-EncodedCommand', encoded],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        elif shutil.which('notify-send'):
            subprocess.Popen(['notify-send', title, message])
    except OSError:
        pass


class Reminders:
    def __init__(self, controller, autostart=True, clock=time.time, idle=idle_seconds, send=notify):
        self.controller = controller
        self.clock, self.idle, self.send = clock, idle, send
        self.path = controller.runtime / 'reminders.json'
        try:
            self.enabled = bool(json.loads(self.path.read_text(encoding='utf-8')).get('enabled', True))
        except (OSError, ValueError, AttributeError):
            self.enabled = True
        self.active_since = None
        self.last_forgot = None
        self.late_day = None
        self.latest = None  # (time, message) for the web page
        self.stopping = threading.Event()
        self.thread = None
        if autostart:
            self.thread = threading.Thread(target=self._run, name='reminders', daemon=True)
            self.thread.start()

    def set_enabled(self, value):
        self.enabled = bool(value)
        atomic_json_write(self.path, {'enabled': self.enabled})
        if not self.enabled:
            self.latest = None

    def current(self):
        if self.latest and self.clock() - self.latest[0] < SHOW_FOR:
            return self.latest[1]
        return None

    def _remind(self, message, now):
        self.latest = (now, message)
        self.send(message)

    def tick(self):
        controller = self.controller
        with controller.lock:
            if controller.closed or not controller.owner or not self.enabled:
                self.active_since = None
                return
            working = controller._running('agent') and not is_paused(controller.control)
        now = self.clock()
        local = datetime.fromtimestamp(now)
        if working:
            self.active_since = None
            if local.hour >= LATE_HOUR and self.late_day != local.date():
                self.late_day = local.date()
                self._remind(LATE, now)
            return
        if local.weekday() not in WORK_DAYS or local.hour not in WORK_HOURS:
            self.active_since = None
            return
        try:
            idle = self.idle()
        except AgentError:
            return  # No permission or unsupported platform: stay quiet.
        if idle > ACTIVE_IDLE_LIMIT:
            self.active_since = None
            return
        if self.active_since is None:
            self.active_since = now
        recently = self.last_forgot is not None and now - self.last_forgot < FORGOT_REPEAT
        if now - self.active_since >= FORGOT_AFTER and not recently:
            self.last_forgot = now
            self._remind(FORGOT, now)

    def _run(self):
        while not self.stopping.wait(30):
            try:
                self.tick()
            except Exception:  # noqa: BLE001  A reminder must never stop the launcher.
                pass

    def close(self):
        self.stopping.set()
