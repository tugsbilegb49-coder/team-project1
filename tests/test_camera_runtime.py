import json
from unittest.mock import Mock, patch
import signal
import pytest

from src.camera_capture import open_camera, CameraPermissionError
from desktop.camera_runtime import read_session, signal_owned_session, ensure_host


@pytest.mark.parametrize(
    'status,reply',
    [('denied', None), ('restricted', None), ('not_determined', 'denied'), ('not_determined', 'timeout')],
)
def test_denied_or_pending_mac_permission_never_opens_capture(status, reply):
    native = Mock()
    native.permission_status.return_value = status
    native.request_permission.return_value = reply
    cv = Mock()
    with (
        patch('src.camera_capture.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': native, 'cv2': cv}),
    ):
        with pytest.raises(CameraPermissionError):
            open_camera(0)
    cv.VideoCapture.assert_not_called()
    assert native.request_permission.called == (status == 'not_determined')


def test_granted_permission_opens_camera_only_after_native_authorization():
    native = Mock()
    native.permission_status.return_value = 'not_determined'
    native.request_permission.return_value = 'authorized'
    cv = Mock()
    with (
        patch('src.camera_capture.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': native, 'cv2': cv}),
    ):
        assert open_camera(2) is cv.VideoCapture.return_value
    cv.VideoCapture.assert_called_once_with(2)


def test_pause_or_consent_revocation_during_os_prompt_prevents_capture():
    allowed = [True]
    native = Mock()
    cv = Mock()
    native.permission_status.return_value = 'not_determined'

    def grant():
        allowed[0] = False
        return 'authorized'

    native.request_permission.side_effect = grant
    with (
        patch('src.camera_capture.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': native, 'cv2': cv}),
    ):
        assert open_camera(0, permitted=lambda: allowed[0]) is None
    cv.VideoCapture.assert_not_called()


def test_native_host_bypasses_reexec_but_plain_python_uses_wrapper():
    with (
        patch('desktop.camera_runtime.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': None}),
        patch('desktop.camera_runtime.os.execv') as execute,
    ):
        ensure_host(['--consent', '--seconds', '1'])
        assert execute.call_args.args[1][-3:] == ['--consent', '--seconds', '1']
    with (
        patch('desktop.camera_runtime.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': Mock()}),
        patch('desktop.camera_runtime.os.execv') as execute,
    ):
        ensure_host(['--consent'])
        execute.assert_not_called()


def test_session_validation_and_stop_cannot_target_an_unrelated_process(tmp_path):
    path = tmp_path / 'session.json'
    path.write_text(json.dumps({'session': 'mine', 'pid': 12345, 'complete': False}))
    assert read_session(path, 'other') is None
    value = read_session(path, 'mine')
    expected = tmp_path / 'WorkTrackCamera'
    with (
        patch('desktop.camera_runtime.subprocess.check_output', return_value='unrelated\n'),
        patch('desktop.camera_runtime.os.kill') as kill,
    ):
        signal_owned_session(value, expected, signal.SIGINT)
        kill.assert_not_called()
    with (
        patch('desktop.camera_runtime.subprocess.check_output', return_value=str(expected) + '\n'),
        patch('desktop.camera_runtime.os.kill') as kill,
    ):
        signal_owned_session(value, expected, signal.SIGINT)
        kill.assert_called_once_with(12345, signal.SIGINT)


def test_cancel_finds_native_pid_that_appears_during_launch_grace(tmp_path):
    from desktop import camera_runtime as runtime

    state = tmp_path / 'late.json'
    permit = tmp_path / 'late.permit.json'
    permit.write_text('{}')
    executable = tmp_path / 'WorkTrackCamera'
    clock = [0.0]
    running = [True]
    signals = []
    opener = Mock()
    opener.poll.side_effect = lambda: None if running[0] else 0

    def advance(seconds):
        clock[0] += seconds
        state.write_text(json.dumps({'session': 'late', 'pid': 12345, 'complete': False}))

    def stop(value, expected, signum):
        if value is None:
            return
        assert not permit.exists(), 'Cancellation must revoke launch permission before signalling.'
        assert expected == executable
        signals.append((value['pid'], signum))
        running[0] = False

    with (
        patch.object(runtime.time, 'monotonic', side_effect=lambda: clock[0]),
        patch.object(runtime.time, 'sleep', side_effect=advance),
        patch.object(runtime, 'signal_owned_session', side_effect=stop),
    ):
        runtime.cancel_session(state, 'late', executable, opener, permit, timeout=0.3)
    assert signals == [(12345, signal.SIGINT)]
    assert not permit.exists()


def test_cancel_revokes_launch_permission_even_before_native_pid_exists(tmp_path):
    from desktop import camera_runtime as runtime

    state = tmp_path / 'missing.json'
    permit = tmp_path / 'missing.permit.json'
    permit.write_text('{}')
    opener = Mock()
    opener.poll.return_value = 0
    with patch.object(runtime, 'signal_owned_session') as stop:
        runtime.cancel_session(state, 'missing', tmp_path / 'WorkTrackCamera', opener, permit, timeout=0)
    assert not permit.exists()
    assert all(call.args[0] is None for call in stop.call_args_list)


def test_cancelled_native_session_prevents_capture_after_permission_dialog():
    from src import camera_capture as capture

    active = [True]
    native = Mock()
    cv = Mock()
    native.session_active.side_effect = lambda: active[0]
    native.permission_status.return_value = 'not_determined'

    def grant():
        active[0] = False
        return 'authorized'

    native.request_permission.side_effect = grant
    with (
        patch('src.camera_capture.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': native, 'cv2': cv}),
    ):
        with pytest.raises(capture.CameraSessionCancelled):
            capture.open_camera(0)
    cv.VideoCapture.assert_not_called()


def test_native_session_check_fails_closed_when_wrapper_has_cancelled():
    from src import camera_capture as capture

    native = Mock()
    native.session_active.return_value = False
    with (
        patch('src.camera_capture.sys.platform', 'darwin'),
        patch.dict('sys.modules', {'_worktrack_camera_host': native}),
    ):
        with pytest.raises(capture.CameraSessionCancelled):
            capture.check_session()


def test_unopened_windows_camera_explains_the_privacy_setting():
    from src.camera_capture import unopened_camera_error

    with patch('src.camera_capture.sys.platform', 'win32'):
        error = unopened_camera_error()
    assert isinstance(error, CameraPermissionError)  # main.py turns this into exit 77 ("permission").
    assert 'Let desktop apps access your camera' in str(error)
    with patch('src.camera_capture.sys.platform', 'darwin'):
        assert not isinstance(unopened_camera_error(), CameraPermissionError)
