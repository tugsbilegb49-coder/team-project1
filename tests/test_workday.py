from http.client import HTTPConnection
import json
from unittest.mock import Mock, patch

import pytest

from agent.main import ApiError
from desktop.service import DesktopController, DesktopError, DesktopServer
from desktop.tray import can_start, start_label, status_text

USER = {'id': 1, 'username': 'worker'}


class FakeServer:
    """The organisation's server as the task timer endpoints answer."""

    def __init__(self):
        self.calls = []
        self.session = None
        self.refuse_start = None

    def state(self):
        return {'session': self.session}

    def get(self, route):
        self.calls.append(('GET', route))
        return self.state()

    def _authenticated_post(self, route, payload):
        self.calls.append(('POST', route, payload))
        if route.endswith('/work-start/'):
            if self.refuse_start:
                raise ApiError(self.refuse_start, 'refused', route=route)
            task = int(route.split('/')[3])
            self.session = {'id': 7, 'task_id': task, 'title': 'Тайлан бэлдэх', 'running': True}
        elif route.endswith('/work-stop/'):
            self.session = None
        return self.state()


@pytest.fixture
def setup(tmp_path):
    (tmp_path / 'agent').mkdir()
    (tmp_path / 'agent/config.example.json').write_text(json.dumps({'productive_apps': []}))
    process = Mock()
    process.poll.return_value = None
    opened = []
    controller = DesktopController(
        tmp_path, 'http://server', 'python', Mock(), spawn=Mock(return_value=process), stop=Mock(), sync=False,
        open_page=lambda: opened.append(True),
    )  # fmt: skip
    controller.backend = Mock(
        return_value={'user_id': 1, 'username': 'worker', 'device_id': 'd', 'access': 'a', 'refresh': 'r'}
    )
    controller.act(USER, 'access', 'connect', {'device_name': 'Laptop', 'consent': True})
    server = FakeServer()
    with (
        patch.object(controller, '_client', return_value=server),
        patch.object(controller, '_require_consent'),
        patch('desktop.workday.ApiClient', return_value=server),
    ):
        yield controller, server, opened
    controller.close()


def test_the_task_started_last_is_offered_next_time(setup):
    controller, _, _ = setup
    assert controller.state(USER)['last_task'] is None
    controller.act(USER, 'a', 'remember-task', {'task': '12', 'title': 'Тайлан бэлдэх'})
    assert controller.state(USER)['last_task'] == {'task': '12', 'title': 'Тайлан бэлдэх'}
    assert controller.state({'id': 2, 'username': 'other'})['last_task'] is None
    for bad in ({'task': '12; rm'}, {'task': 12}, {'task': '1', 'extra': 1}):
        with pytest.raises(DesktopError):
            controller.act(USER, 'a', 'remember-task', bad)


def test_tray_start_uses_the_remembered_task_and_starts_recording(setup):
    controller, server, opened = setup
    assert controller.tray_act('start')['message'].startswith('Хийх даалгавраа')  # Nothing remembered yet.
    assert opened == [True]
    controller.act(USER, 'a', 'remember-task', {'task': '12', 'title': 'Тайлан бэлдэх'})
    state = controller.tray_act('start')
    assert ('POST', '/api/tasks/12/work-start/', {}) in server.calls
    assert state['working'] and state['task'] == 'Тайлан бэлдэх' and state['next_task'] == 'Тайлан бэлдэх'
    state = controller.tray_act('pause')
    assert state['paused'] and not state['working'] and server.session is None
    assert ('POST', '/api/tasks/12/work-stop/', {'session_id': 7}) in server.calls
    assert controller.tray_act('start')['working']  # Resumes.
    state = controller.tray_act('finish')
    assert not state['running'] and server.session is None


def test_a_finished_or_moved_task_is_forgotten_and_the_page_opens(setup):
    controller, server, opened = setup
    controller.act(USER, 'a', 'remember-task', {'task': '12', 'title': 'Хуучин ажил'})
    server.refuse_start = 409
    result = controller.tray_act('start')
    assert 'Хуучин ажил' in result['message'] and opened == [True]
    assert not result['running'] and controller.state(USER)['last_task'] is None


def test_without_a_task_only_app_use_is_recorded(setup):
    controller, server, _ = setup
    controller.act(USER, 'a', 'remember-task', {'task': 'none'})
    state = controller.tray_act('start')
    assert state['working'] and state['task'] is None and state['next_task'] == 'Даалгаваргүй'
    assert not any('work-start' in call[1] for call in server.calls)


def test_the_task_timer_stays_alive_without_the_web_page(setup):
    controller, server, _ = setup
    controller.workday.beat()
    assert server.calls == []  # Not recording: nothing to keep alive.
    controller.act(USER, 'a', 'start', {})
    server.session = {'id': 9, 'task_id': 3, 'title': 'Page task', 'running': True}  # Started on the page.
    controller.workday.beat()
    assert server.calls == [
        ('GET', '/api/tasks/work-session/'),
        ('POST', '/api/tasks/work-session/', {'session_id': 9}),
    ]
    controller.workday.beat()
    assert server.calls[-1] == ('POST', '/api/tasks/work-session/', {'session_id': 9})
    controller.act(USER, 'a', 'pause', {})
    calls = len(server.calls)
    controller.workday.beat()
    assert len(server.calls) == calls  # Paused: the timer is allowed to end.


def test_tray_endpoint_needs_the_launchers_secret_and_no_browser(setup):
    controller, _, _ = setup
    server = DesktopServer(('127.0.0.1', 0), controller, {'http://127.0.0.1:5173'})
    server.start()

    def call(method, path, headers):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        connection.request(method, path, headers={'Host': f'127.0.0.1:{server.server_port}', **headers})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    try:
        secret = {'X-WorkTrack-Tray': controller.tray_secret}
        assert call('GET', '/desktop/tray/', {})[0] == 403
        assert call('GET', '/desktop/tray/', {'X-WorkTrack-Tray': 'guess'})[0] == 403
        assert call('GET', '/desktop/tray/', {**secret, 'Origin': 'https://evil.example'})[0] == 403
        status, state = call('GET', '/desktop/tray/', secret)
        assert status == 200 and state['linked'] and not state['working']
        assert call('POST', '/desktop/tray/reboot/', secret)[0] == 404
        controller.closed = True
        assert call('GET', '/desktop/tray/', secret)[0] == 409  # Tells the icon to go away.
        controller.closed = False
    finally:
        server.close()


def test_the_menu_reads_the_state():
    assert status_text(None) == 'WorkTrack холбогдож байна…'
    idle = {'linked': True, 'working': False, 'paused': False, 'running': False, 'task': None}
    assert status_text(idle) == '○ Ажил эхлээгүй' and start_label(idle) == 'Ажил эхлүүлэх…'
    remembered = {**idle, 'next_task': 'Тайлан', 'next_is_task': True}
    assert start_label(remembered) == 'Ажил эхлүүлэх: Тайлан' and can_start(remembered)
    working = {**remembered, 'working': True, 'running': True, 'task': 'Тайлан'}
    assert status_text(working) == '● Бүртгэж байна · Тайлан' and not can_start(working)
    lost_timer = {**working, 'task': None}  # E.g. the computer slept and the server ended the timer.
    assert can_start(lost_timer) and start_label(lost_timer) == 'Даалгаврын цаг эхлүүлэх: Тайлан'
    assert not can_start({'linked': False})


def test_a_tray_icon_that_went_away_is_started_again_a_few_times(tmp_path):
    (tmp_path / 'agent').mkdir()
    (tmp_path / 'agent/config.example.json').write_text(json.dumps({'productive_apps': []}))
    gone = Mock()
    gone.poll.return_value = 0
    spawn = Mock(return_value=gone)
    controller = DesktopController(
        tmp_path, 'http://server', 'python', Mock(), spawn=spawn, stop=Mock(), sync=False, tray_command=['tray']
    )
    try:
        assert spawn.call_args.args[2] == {'WORKTRACK_TRAY_SECRET': controller.tray_secret}
        for _ in range(5):
            state = controller.state(USER)
        assert spawn.call_count == 4  # The first start and three more.
        assert state['tray_running'] is False and state['tray_restarts'] == 3 and state['tray_exit'] == 0
    finally:
        controller.close()
