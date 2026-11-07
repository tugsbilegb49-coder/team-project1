import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Event
from unittest.mock import Mock,patch
import pytest

from desktop.service import DesktopController,DesktopError,DesktopServer


@pytest.fixture
def controller(tmp_path):
    (tmp_path/'agent').mkdir()
    (tmp_path/'agent/config.example.json').write_text(json.dumps({'productive_apps':[],'interval_seconds':30}))
    process=Mock();process.poll.return_value=None
    value=DesktopController(tmp_path,'http://127.0.0.1:8000','python',Mock(),spawn=Mock(return_value=process),stop=Mock(),sync=False)
    value.backend=Mock(return_value={'user_id':1,'username':'worker','device_id':'device','access':'test-access','refresh':'test-refresh'})
    yield value
    value.close()


USER={'id':1,'username':'worker'}


def link(controller):
    return controller.act(USER,'access','connect',{'device_name':'Laptop','consent':True})


def test_launcher_uptime_comes_from_process_start_not_browser_or_account(controller):
    controller.started_at = 1000
    with patch.object(controller.usage, 'snapshot', return_value={}), patch('desktop.service.time.time', return_value=1123):
        assert controller.state(USER)['launcher_uptime_seconds'] == 123
        assert controller.state({'id':2,'username':'other'})['launcher_started_at'] == 1000
    with patch.object(controller.usage, 'snapshot', return_value={}), patch('desktop.service.time.time', return_value=1200):
        assert controller.state(USER)['launcher_uptime_seconds'] == 200


def test_onboarding_and_start_pause_camera_stop_use_only_owned_processes(controller):
    with pytest.raises(DesktopError):controller.act(USER,'access','connect',{'consent':False})
    assert link(controller)['linked']
    assert not controller.spawn.called
    with patch.object(controller,'_require_consent'),patch('desktop.service.importlib.util.find_spec',return_value=True):
        assert controller.act(USER,'access','start',{})['computer_running']
        controller.act(USER,'access','start',{})
        assert controller.spawn.call_count==1
        assert controller.act(USER,'access','pause',{})['paused']
        with pytest.raises(DesktopError):controller.act(USER,'access','camera-on',{})
        controller.act(USER,'access','resume',{})
        controller.act(USER,'access','camera-on',{})
        assert '--consent' in controller.spawn.call_args.args[1]
        controller.act(USER,'access','camera-off',{})
        assert controller.stop.call_count==1
        controller.act(USER,'access','stop',{})
        assert controller.stop.call_count==2


def test_different_web_account_cannot_control_or_replace_running_collectors(controller):
    link(controller)
    other={'id':2,'username':'other'}
    for action in ('start','stop','pause','disconnect','quit'):
        with pytest.raises(DesktopError) as error:controller.act(other,'access',action,{})
        assert error.value.status==403
    with patch.object(controller,'_require_consent'):
        controller.act(USER,'access','start',{})
    with pytest.raises(DesktopError):controller.act(other,'access','connect',{'device_name':'Other','consent':True})
    state=controller.state(other)
    assert state['another_account'] and state['device_name'] is None
    assert state['launcher_usage']['last_upload'] is None
    assert not state['launcher_usage']['running']
    assert state['launcher_usage']['months'][0]['seconds'] == 0
    assert not controller.stop.called


def test_saved_agent_identity_and_consent_are_checked_before_start(controller):
    link(controller)
    with patch('desktop.service.ApiClient') as client:
        client.return_value.get.return_value={'id':2}
        with pytest.raises(DesktopError):controller.act(USER,'access','start',{})
        client.return_value.get.side_effect=[USER,{'active':False}]
        with pytest.raises(DesktopError):controller.act(USER,'access','start',{})
    assert not controller.spawn.called


def test_http_bridge_rejects_cross_origin_bad_host_missing_auth_and_large_body(controller):
    controller.authenticate=Mock(return_value=(USER,'access'))
    server=DesktopServer(('127.0.0.1',0),controller,{'http://127.0.0.1:5173'});server.start()
    try:
        def request(method,path,body=None,**headers):
            connection=HTTPConnection(*server.server_address,timeout=3)
            connection.request(method,path,body=body,headers=headers)
            response=connection.getresponse();code=response.status;response.read();connection.close();return code
        valid={'Origin':'http://127.0.0.1:5173','X-WorkTrack-Desktop':'1','Authorization':'Bearer access','Content-Type':'application/json'}
        assert request('POST','/desktop/start/',body='{}',**{**valid,'Origin':'https://foreign.example'})==403
        assert request('POST','/desktop/start/',body='{}',**{**valid,'Host':'foreign.example'})==403
        assert request('GET','/desktop/status/')==403
        assert request('OPTIONS','/desktop/start/',**valid)==403
        assert request('POST','/desktop/start/',body='x'*9000,**valid)==413
        assert request('POST','/desktop/shell/',body='{}',**valid)==404
        assert request('GET','/desktop/status/',**valid)==200
        assert not controller.spawn.called
    finally:server.close()


def test_collector_lock_prevents_duplicate_collector():
    from agent.process_lock import collector_lock,AlreadyRunningError
    with collector_lock('test-only'):
        with pytest.raises(AlreadyRunningError):
            with collector_lock('test-only'):pass


@pytest.mark.parametrize('matching_instance,matching_process,should_stop',[(True,True,True),(False,True,False),(True,False,False)])
def test_native_quit_requires_owned_instance_and_uses_absolute_tools(tmp_path,matching_instance,matching_process,should_stop):
    from desktop import app_control
    import signal
    instance='a2dab676-772a-4776-a297-31c22639398f'
    other='b2dab676-772a-4776-a297-31c22639398f'
    (tmp_path/'.runtime').mkdir()
    (tmp_path/'.runtime/macos-app.json').write_text(json.dumps({'pid':12345,'instance':instance if matching_instance else other}))
    command=str(tmp_path/'worktrack.py')+' --desktop --app-id '+instance if matching_process else 'unrelated process'
    with patch.object(app_control,'ROOT',tmp_path),patch.object(app_control.sys,'argv',['app_control.py','stop',instance]), \
         patch.object(app_control.subprocess,'check_output',side_effect=[command,'p12345\nfcwd\nn'+str(tmp_path)+'\n']) as read, \
         patch.object(app_control.os,'kill') as kill:
        app_control.main()
    assert kill.called==should_stop
    if should_stop:
        kill.assert_called_once_with(12345,signal.SIGTERM)
        assert read.call_args_list[0].args[0][0]=='/bin/ps'
        assert read.call_args_list[1].args[0][0]=='/usr/sbin/lsof'
