"""Start WorkTrack when the user signs in to the computer (per user; no administrator rights).

Windows: a value under HKCU\\...\\Run. macOS: a LaunchAgent plist. Linux: an XDG autostart entry.
WorkTrack then starts in the background without opening the browser. Starting the program does not
start recording: the employee still presses «Ажил эхлүүлэх», and the reminders say so if they forget.
"""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

LABEL = 'mn.worktrack.client'
NAME = 'WorkTrack'  # The Run value's name on Windows.
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def supported():
    return sys.platform in ('win32', 'darwin') or sys.platform.startswith('linux')


def mac_plist():
    return Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'


def linux_entry():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'autostart' / 'worktrack.desktop'


def windows_command(command):
    # `start "" /min` keeps the console window of the Windows build minimised at sign-in; the
    # empty quoted first argument is the window title, so a quoted program path is not taken for it.
    return 'cmd.exe /d /c start "" /min ' + subprocess.list2cmdline(command)


def desktop_exec(command):
    """Quote arguments for the Exec= key of a .desktop file."""

    def quote(value):
        for char in ('\\', '"', '`', '$'):
            value = value.replace(char, '\\' + char)
        return f'"{value}"'

    return ' '.join(quote(part) for part in command).replace('%', '%%')


def current():
    """The command registered to start at sign-in, as text, or None."""
    try:
        if sys.platform == 'win32':
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return winreg.QueryValueEx(key, NAME)[0]
        if sys.platform == 'darwin':
            with mac_plist().open('rb') as stream:
                return ' '.join(plistlib.load(stream)['ProgramArguments'])
        for line in linux_entry().read_text(encoding='utf-8').splitlines():
            if line.startswith('Exec='):
                return line[5:]
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException):
        return None
    return None


def expected(command):
    if sys.platform == 'win32':
        return windows_command(command)
    if sys.platform == 'darwin':
        return ' '.join(command)
    return desktop_exec(command)


def enable(command, log=None):
    """Register `command` to run at sign-in, replacing an older entry (e.g. after the app moved)."""
    if sys.platform == 'win32':
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, windows_command(command))
        return
    if sys.platform == 'darwin':
        from agent.token_store import atomic_write_bytes

        job = {
            'Label': LABEL,
            'ProgramArguments': list(command),
            'RunAtLoad': True,
            'ProcessType': 'Interactive',
            'LimitLoadToSessionType': 'Aqua',
        }
        if log:
            job['StandardOutPath'] = job['StandardErrorPath'] = str(log)
        mac_plist().parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(mac_plist(), plistlib.dumps(job))
        return
    from agent.token_store import atomic_write_bytes

    entry = (
        '[Desktop Entry]\nType=Application\nName=WorkTrack\n'
        f'Exec={desktop_exec(command)}\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n'
    )
    linux_entry().parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(linux_entry(), entry.encode('utf-8'))


def disable():
    if sys.platform == 'win32':
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, NAME)
        except FileNotFoundError:
            pass
        return
    (mac_plist() if sys.platform == 'darwin' else linux_entry()).unlink(missing_ok=True)


class Autostart:
    """Start-at-sign-in for this copy of WorkTrack, kept pointing at the current program location."""

    def __init__(self, command, log=None, platform_ok=None):
        self.command, self.log = list(command or []), log
        self.supported = bool(self.command) and (supported() if platform_ok is None else platform_ok)
        if self.supported and self.enabled and current() != expected(self.command):
            self.set(True)  # The program was moved or updated: point the entry at this copy.

    @property
    def enabled(self):
        return self.supported and current() is not None

    def set(self, value):
        if not self.supported:
            raise OSError('Автоматаар асаах боломжгүй.')
        if value:
            enable(self.command, self.log)
        else:
            disable()
