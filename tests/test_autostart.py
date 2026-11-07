import json
import plistlib
import sys
import types
from unittest.mock import Mock, patch

import pytest

from desktop import autostart
from desktop.autostart import Autostart
from desktop.service import DesktopController, DesktopError

COMMAND = ['/Applications/Work Track.app/Contents/MacOS/WorkTrack', '--no-browser']


@pytest.fixture
def mac(tmp_path):
    with patch.object(autostart.sys, 'platform', 'darwin'), patch.object(autostart.Path, 'home', return_value=tmp_path):
        yield tmp_path / 'Library' / 'LaunchAgents' / 'mn.worktrack.client.plist'


@pytest.fixture
def windows():
    """A stand-in for winreg that keeps the Run key in a dict."""
    values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def query(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    def delete(key, name):
        if name not in values:
            raise FileNotFoundError(name)
        del values[name]

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER='HKCU',
        KEY_SET_VALUE=2,
        REG_SZ=1,
        OpenKey=lambda *args: Key(),
        CreateKey=lambda *args: Key(),
        QueryValueEx=query,
        SetValueEx=lambda key, name, reserved, kind, value: values.__setitem__(name, value),
        DeleteValue=delete,
    )
    with patch.object(autostart.sys, 'platform', 'win32'), patch.dict(sys.modules, {'winreg': fake}):
        yield values


def test_macos_launch_agent_starts_the_app_in_the_background_and_logs(mac, tmp_path):
    item = Autostart(COMMAND, log=tmp_path / 'app.log')
    assert item.supported and not item.enabled
    item.set(True)
    job = plistlib.loads(mac.read_bytes())
    assert job['ProgramArguments'] == COMMAND and job['RunAtLoad'] is True
    assert job['StandardOutPath'] == str(tmp_path / 'app.log')
    assert item.enabled
    item.set(False)
    assert not mac.exists() and not item.enabled


def test_moved_program_updates_the_existing_entry(mac):
    Autostart(['/old/place/WorkTrack', '--no-browser']).set(True)
    Autostart(COMMAND)  # Started from the new place.
    assert plistlib.loads(mac.read_bytes())['ProgramArguments'] == COMMAND


def test_a_turned_off_entry_is_not_turned_back_on_by_starting(mac):
    Autostart(COMMAND)
    assert not mac.exists()


def test_windows_run_value_quotes_the_path_and_starts_minimised(windows):
    command = [r'C:\Users\Бат Эрдэнэ\Downloads\WorkTrack\WorkTrack.exe', '--no-browser']
    item = Autostart(command)
    item.set(True)
    assert windows['WorkTrack'] == (
        r'cmd.exe /d /c start "" /min "C:\Users\Бат Эрдэнэ\Downloads\WorkTrack\WorkTrack.exe" --no-browser'
    )
    assert item.enabled
    item.set(False)
    assert windows == {} and not item.enabled
    item.set(False)  # Already off: no error.


def test_linux_autostart_entry_quotes_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    with patch.object(autostart.sys, 'platform', 'linux'):
        Autostart(['/opt/work track/WorkTrack', '--name=$HOME']).set(True)
    text = (tmp_path / 'autostart' / 'worktrack.desktop').read_text(encoding='utf-8')
    assert 'Exec="/opt/work track/WorkTrack" "--name=\\$HOME"\n' in text


def test_without_a_command_nothing_is_offered():
    item = Autostart(None)
    assert not item.supported and not item.enabled
    with pytest.raises(OSError):
        item.set(True)


@pytest.fixture
def controller(tmp_path, mac):
    (tmp_path / 'agent').mkdir()
    (tmp_path / 'agent/config.example.json').write_text(json.dumps({'productive_apps': []}))
    value = DesktopController(
        tmp_path, 'http://127.0.0.1:8000', 'python', Mock(), spawn=Mock(), stop=Mock(), sync=False,
        autostart_command=COMMAND,
    )  # fmt: skip
    value.backend = Mock(
        return_value={'user_id': 1, 'username': 'worker', 'device_id': 'd', 'access': 'a', 'refresh': 'r'}
    )
    yield value
    value.close()


USER = {'id': 1, 'username': 'worker'}


def connect(controller):
    return controller.act(USER, 'access', 'connect', {'device_name': 'Laptop', 'consent': True})


def test_installed_app_turns_autostart_on_when_a_device_is_linked(controller):
    with patch('desktop.service.FROZEN', True):
        assert controller.state(USER)['autostart_on_connect'] is True
        assert connect(controller)['autostart_enabled'] is True


def test_a_users_choice_is_kept_when_linking_again(controller):
    with patch('desktop.service.FROZEN', True):
        state = controller.act(USER, 'access', 'autostart-off', {})  # Before linking: e.g. the office server.
        assert state['autostart_enabled'] is False and state['autostart_on_connect'] is False
        assert connect(controller)['autostart_enabled'] is False


def test_source_checkout_never_turns_autostart_on_by_itself(controller):
    assert connect(controller)['autostart_enabled'] is False
    assert controller.act(USER, 'access', 'autostart-on', {})['autostart_enabled'] is True


def test_someone_else_cannot_change_a_linked_computer(controller):
    connect(controller)
    with pytest.raises(DesktopError) as error:
        controller.act({'id': 2, 'username': 'other'}, 'access', 'autostart-on', {})
    assert error.value.status == 403
