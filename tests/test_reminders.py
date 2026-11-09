from datetime import datetime
import json
from pathlib import Path
import threading
from unittest.mock import patch

import pytest

from agent.main import AgentError
from desktop import reminders
from desktop.reminders import FORGOT, LATE, Reminders


def at(text):
    return datetime.fromisoformat(text).timestamp()


class Fake:
    """A controller with just what Reminders reads, plus a controllable clock and idle time."""

    def __init__(self, tmp_path, working=False, linked=True):
        self.runtime = Path(tmp_path)
        self.control = self.runtime / 'control.json'
        self.lock = threading.RLock()
        self.closed = False
        self.owner = {'user_id': 1} if linked else None
        self.working = working
        self.now = at('2026-11-04T10:00:00')  # A Wednesday morning.
        self.idle = 5.0
        self.sent = []

    def _running(self, name):
        return self.working

    def reminders(self):
        return Reminders(self, autostart=False, clock=lambda: self.now, idle=self.read_idle, send=self.sent.append)

    def read_idle(self):
        if isinstance(self.idle, Exception):
            raise self.idle
        return self.idle


def run(fake, item, minutes, step=0.5):
    for _ in range(int(minutes / step)):
        item.tick()
        fake.now += step * 60


def test_forgotten_start_reminds_after_ten_active_minutes_then_waits_two_hours(tmp_path):
    fake = Fake(tmp_path)
    item = fake.reminders()
    run(fake, item, 9.5)
    assert fake.sent == []
    run(fake, item, 1)
    assert fake.sent == [FORGOT]
    assert item.current() == FORGOT
    run(fake, item, 60)
    assert fake.sent == [FORGOT]  # No nagging within two hours.


def test_no_forgot_reminder_while_away_outside_work_hours_or_without_idle_access(tmp_path):
    for change in (
        {'idle': 600.0},  # Nobody at the computer.
        {'now': at('2026-11-04T21:00:00')},  # Evening.
        {'now': at('2026-11-07T10:00:00')},  # Saturday.
        {'idle': AgentError('no permission')},
        {'owner': None},  # Not linked.
    ):
        fake = Fake(tmp_path)
        for key, value in change.items():
            setattr(fake, key, value)
        item = fake.reminders()
        run(fake, item, 15)
        assert fake.sent == [], change


def test_late_work_reminds_once_per_evening(tmp_path):
    fake = Fake(tmp_path, working=True)
    fake.now = at('2026-11-04T18:58:00')  # The default schedule ends at 18:00; an hour later counts as late.
    item = fake.reminders()
    run(fake, item, 2)
    assert fake.sent == []
    run(fake, item, 120)
    assert fake.sent == [LATE]
    fake.now = at('2026-11-05T19:30:00')
    item.tick()
    assert fake.sent == [LATE, LATE]


def test_paused_work_counts_as_not_working(tmp_path):
    fake = Fake(tmp_path, working=True)
    fake.control.write_text(json.dumps({'paused': True}), encoding='utf-8')
    item = fake.reminders()
    run(fake, item, 11)
    assert fake.sent == [FORGOT]


def test_turning_reminders_off_is_remembered(tmp_path):
    fake = Fake(tmp_path)
    item = fake.reminders()
    item.set_enabled(False)
    run(fake, item, 15)
    assert fake.sent == []
    assert fake.reminders().enabled is False  # Survives a restart.


@pytest.mark.parametrize('platform', ['darwin', 'win32'])
def test_notification_text_is_passed_as_data_not_code(platform):
    message = "Ажил'; rm -rf / #"
    with patch.object(reminders.sys, 'platform', platform), patch.object(reminders.subprocess, 'Popen') as popen:
        reminders.notify(message)
    command = popen.call_args.args[0]
    if platform == 'darwin':
        assert command[0] == '/usr/bin/osascript' and command[-2:] == [message, 'WorkTrack']
    else:
        import base64

        script = base64.b64decode(command[-1]).decode('utf-16-le')
        assert "'Ажил''; rm -rf / #'" in script  # Single quotes doubled inside a PowerShell string.


def test_notification_failure_is_ignored():
    with (
        patch.object(reminders.sys, 'platform', 'darwin'),
        patch.object(reminders.subprocess, 'Popen', side_effect=OSError),
    ):
        reminders.notify('hello')


def test_the_organisations_schedule_decides_when_to_remind(tmp_path):
    fake = Fake(tmp_path)
    fake.schedule = {'days': {0, 1, 2, 3, 4}, 'start': 14 * 60, 'end': 20 * 60}  # Classes in the morning.
    item = fake.reminders()
    run(fake, item, 15)  # 10:00–10:15 on a Wednesday: class time.
    assert fake.sent == []
    fake.now = at('2026-11-04T14:30:00')
    run(fake, item, 11)
    assert fake.sent == [FORGOT]


def test_the_schedule_is_read_from_the_server_settings():
    from desktop.workday import parse_schedule

    value = parse_schedule({'work_days': [4, 0], 'work_start': '13:30:00', 'work_end': '19:00'})
    assert value == {'days': {0, 4}, 'start': 13 * 60 + 30, 'end': 19 * 60}
