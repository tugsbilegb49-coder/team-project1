from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.runtime import AgentRuntime
from src.camera_session import CameraSession


def test_runtime_heartbeat_reports_real_queue_state_and_preserves_settings_on_failure():
    client=Mock();client.get.return_value={'version':2,'productive_apps':['Code'],'camera_threshold':.7}
    worker=SimpleNamespace(lock=threading.Lock(),pending=[{},{}],last_upload_at=None,last_error='network')
    runtime=AgentRuntime(client,'device-uuid',worker,lambda:True)
    assert runtime.cycle()
    sent=client._authenticated_post.call_args.args[1]
    assert sent['queue_count']==2 and sent['paused'] and sent['settings_version']==2
    assert sent['error_code']=='network'
    client.get.side_effect=OSError('offline')
    assert not runtime.cycle()
    assert runtime.snapshot()['version']==2


def test_all_camera_sessions_enforce_timeout_without_opening_hardware_when_denied(tmp_path):
    cv,guard=Mock(),Mock();guard.allowed.return_value=False;cv.waitKey.return_value=-1
    session=CameraSession({'camera_index':0,'control_file':str(tmp_path/'control.json')},guard,seconds=1)
    with patch.dict('sys.modules',{'cv2':cv}),patch('src.camera_session.time.monotonic',side_effect=[0,0,2]),patch('src.camera_session.time.sleep'):
        assert list(session.frames())==[]
        session.close()
    cv.VideoCapture.assert_not_called()


def test_legacy_entry_forwards_seconds_and_does_not_import_multi_person_dependencies(tmp_path):
    import importlib.util
    module=SimpleNamespace(WorkerActivityMonitor=Mock())
    spec=importlib.util.spec_from_file_location('camera_cli_under_test',Path(__file__).resolve().parents[1]/'main.py')
    entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    path=tmp_path/'config.yaml';path.write_text('camera_mode: activity\nmulti_person: false\n')
    with patch.dict('sys.modules',{'src.monitor':module}),patch.object(sys,'argv',['main.py','--config',str(path),'--consent','--seconds','1']),patch('desktop.camera_runtime.ensure_host'):
        entry.main()
    module.WorkerActivityMonitor.return_value.run.assert_called_once_with(seconds=1)


def test_dependency_fingerprints_reinstall_only_changed_manifests(tmp_path):
    import worktrack
    from hashlib import sha256
    (tmp_path/'backend').mkdir();(tmp_path/'backend/requirements.txt').write_text('Django>=5\n')
    (tmp_path/'backend/.env').write_text('# existing private settings\n')
    (tmp_path/'package.json').write_text('{}');(tmp_path/'package-lock.json').write_text('{"version":1}')
    (tmp_path/'node_modules/vite/bin').mkdir(parents=True);(tmp_path/'node_modules/vite/bin/vite.js').touch()
    (tmp_path/'.venv/bin').mkdir(parents=True);(tmp_path/'.venv/bin/python').touch()
    runtime=tmp_path/'.runtime'
    def invoke():
        with patch.object(worktrack,'ROOT',tmp_path),patch.object(worktrack,'RUNTIME',runtime), \
             patch.object(worktrack.sys,'prefix',str(tmp_path/'.venv')), \
             patch.object(worktrack.shutil,'which',return_value='npm'), \
             patch.object(worktrack,'check_http',return_value=False), \
             patch.object(worktrack.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='True\n')) as run:
            worktrack.bootstrap()
            return [call.args[0] for call in run.call_args_list]
    first=invoke()
    assert any(command[:2]==['npm','ci'] for command in first)
    assert any('pip' in command for command in first)
    second=invoke()
    assert not any(command[:2]==['npm','ci'] for command in second)
    assert not any('pip' in command for command in second)
    (tmp_path/'package-lock.json').write_text('{"version":2}')
    third=invoke()
    assert any(command[:2]==['npm','ci'] for command in third)
    assert not any('pip' in command for command in third)
