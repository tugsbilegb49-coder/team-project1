from datetime import timedelta
from django.test import TestCase, LiveServerTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from users.models import User
from activity.models import ComputerActivity
from .models import Task


@override_settings(REQUIRE_MONITORING_CONSENT=False)
class UnifiedFlowTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.admin = User.objects.create_superuser('admin', password='test-pass-very-long-123')
        self.employee = User.objects.create_user('worker', password='test-pass-very-long-123')
        self.client = APIClient()

    def login(self, username):
        response = self.client.post('/api/auth/login/', {'username':username, 'password':'test-pass-very-long-123'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])

    def test_login_task_agent_camera_score_dashboard(self):
        self.login('admin')
        self.assertTrue(self.client.get('/api/users/me/').data['is_admin'])
        today = timezone.localdate().isoformat()
        task = self.client.post('/api/tasks/', {'employee':self.employee.pk, 'title':'Integration', 'due_date':today}, format='json')
        self.assertEqual(task.status_code, 201)
        done = self.client.patch(f'/api/tasks/{task.data["id"]}/', {'status':'DONE','quality_score':90}, format='json')
        self.assertIsNotNone(done.data['completed_at'])
        self.login('worker')
        device = self.client.post('/api/devices/enroll/', {'name':'Laptop','platform':'test'}, format='json').data['id']
        self.client.post('/api/consents/grant/', {'policy_version':'2026-11'}, format='json')
        now = timezone.now()
        app = self.client.post('/api/computer-activity/ingest/', {'device_id':device,'started_at':(now-timedelta(seconds=30)).isoformat(),'duration_seconds':30,'application':'Code','category':'WORK'}, format='json')
        self.assertEqual(app.status_code, 201)
        camera = self.client.post('/api/activity-events/ingest/', {'device_id':device,'timestamp':now.isoformat(),'duration_seconds':30,'state':'WORKING'}, format='json')
        self.assertEqual(camera.status_code, 201)
        score = self.client.post('/api/scores/calculate/', {'date':today}, format='json')
        self.assertEqual(score.status_code, 201)
        dashboard = self.client.get('/api/scores/dashboard/', {'date':today}).data
        self.assertEqual(dashboard['applications'][0]['seconds'], 30)
        self.assertEqual(dashboard['camera'][0]['seconds'], 30)
        self.assertEqual(float(dashboard['score']['score']), 97)

    def batch(self):
        now = timezone.now().replace(microsecond=0)
        return {'schema_version':'1.0','agent_version':'0.1.0','employee_id':'worker','device_id':'hashed-device',
            'period_start':(now-timedelta(seconds=60)).isoformat(),'period_end':now.isoformat(),
            'active_seconds':40,'idle_seconds':20,'keyboard_events':3,'mouse_events':4,
            'apps':[{'name':'Code','seconds':40}]}

    def test_legacy_agent_batch_replay_and_isolation(self):
        self.login('worker')
        batch = self.batch()
        for expected in (201,200):
            self.assertEqual(self.client.post('/api/v1/activity',batch,format='json').status_code,expected)
        self.assertEqual(ComputerActivity.objects.count(),2)
        batch['employee_id']='admin'
        self.assertEqual(self.client.post('/api/v1/activity',batch,format='json').status_code,403)
        self.assertEqual(ComputerActivity.objects.count(),2)

    def test_invalid_batch_is_atomic_and_consent_required(self):
        self.login('worker')
        with self.settings(REQUIRE_MONITORING_CONSENT=True):
            self.assertEqual(self.client.post('/api/v1/activity',self.batch(),format='json').status_code,403)
        batch=self.batch()
        batch['apps'].append({'name':'Invalid','seconds':500})
        self.assertEqual(self.client.post('/api/v1/activity',batch,format='json').status_code,400)
        self.assertEqual(ComputerActivity.objects.count(),0)

    def test_reopened_task_clears_completion(self):
        self.login('admin')
        task=Task.objects.create(employee=self.employee,title='Reopen',status='DONE',completed_at=timezone.now())
        result=self.client.patch(f'/api/tasks/{task.pk}/',{'status':'IN_PROGRESS'},format='json')
        self.assertIsNone(result.data['completed_at'])

    def test_user_create_requires_password(self):
        self.login('admin')
        response=self.client.post('/api/users/',{'username':'missing-password'},format='json')
        self.assertEqual(response.status_code,400)

    def test_manager_without_department_cannot_access_other_employee(self):
        manager = User.objects.create_user('unassigned-manager', password='test-pass-very-long-123', role='MANAGER')
        self.client.force_authenticate(manager)
        self.assertEqual(self.client.post('/api/tasks/', {'employee':self.employee.pk,'title':'Forbidden'}, format='json').status_code,403)
        self.assertEqual(self.client.get('/api/scores/dashboard/', {'employee_id':self.employee.pk}).status_code,403)


@override_settings(REQUIRE_MONITORING_CONSENT=False)
class LiveUploaderTests(LiveServerTestCase):
    """Exercise the real HTTP uploaders against Django, not the mock API."""
    def test_presence_uploader_refresh_consent_and_replay_over_http(self):
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.core.cache import cache
        from users.models import ConsentRecord
        from activity.models import CameraPresence
        cache.clear()
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from src.api_logger import PresenceEventUploader
        user=User.objects.create_user('presence-live-worker',password='test-pass-very-long-123')
        client=APIClient()
        tokens=client.post('/api/auth/login/',{'username':user.username,'password':'test-pass-very-long-123'},format='json').data
        tokens['access']='expired-token'
        consent=ConsentRecord.objects.create(employee=user,granted=True,policy_version='camera-presence-v1')
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'tokens.json').write_text(json.dumps(tokens))
            uploader=PresenceEventUploader(self.live_server_url,str(root/'tokens.json'),str(root/'device.json'),root/'pending.json')
            timestamp=timezone.now()-timedelta(seconds=1)
            try:
                uploader.log(True,.81,timestamp)
                self.assertTrue(uploader.flush(3))
                uploader.log(True,.81,timestamp)
                self.assertTrue(uploader.flush(3))
                self.assertEqual(CameraPresence.objects.filter(employee=user).count(),1)
                consent.revoked_at=timezone.now();consent.save(update_fields=['revoked_at'])
                uploader.log(False,0,timezone.now()-timedelta(milliseconds=10))
                self.assertFalse(uploader.flush(3))
            finally:
                uploader.close()
            self.assertEqual(len(json.loads((root/'pending.json').read_text())),1)
            self.assertEqual(CameraPresence.objects.filter(employee=user).count(),1)

    def test_launcher_recognizes_current_backend_over_http(self):
        import sys
        from pathlib import Path
        from unittest.mock import patch
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        import worktrack
        with patch.object(worktrack,'API',self.live_server_url):
            self.assertTrue(worktrack.backend_is_current())
            # The running server retains the digest captured at startup.
            with patch('backend.config.identity.source_digest',return_value='new-local-code'):
                with self.assertRaisesRegex(RuntimeError,'хуучин'):
                    worktrack.backend_is_current()

    def test_invalid_head_does_not_block_valid_http_upload(self):
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.core.cache import cache
        cache.clear()
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from agent.main import ApiClient, PendingUploader
        user=User.objects.create_user('queue-worker',password='test-pass-very-long-123')
        client=APIClient()
        tokens=client.post('/api/auth/login/',{'username':user.username,'password':'test-pass-very-long-123'},format='json').data
        with TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'tokens.json').write_text(json.dumps(tokens))
            uploader=PendingUploader(ApiClient(self.live_server_url,path/'tokens.json'),path/'pending.json')
            payload={'started_at':(timezone.now()-timedelta(seconds=60)).isoformat(),'duration_seconds':30,'application':'Code','category':'WORK'}
            uploader.append_many([{**payload,'duration_seconds':-1},payload])
            try:
                self.assertTrue(uploader.flush(3))
            finally:
                uploader.stop()
            self.assertEqual(json.loads((path/'pending.json').read_text()),[])
            rejected=json.loads((path/'pending.rejected.json').read_text())
            self.assertEqual(rejected[0]['status'],400)
            self.assertEqual(rejected[0]['event']['duration_seconds'],-1)
            self.assertEqual(ComputerActivity.objects.filter(employee=user).count(),1)

    def test_batch_and_camera_upload_with_refresh(self):
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from activity_agent.sender import BatchSender
        from src.api_logger import CameraEventUploader
        from django.core.cache import cache
        cache.clear()
        user = User.objects.create_user('live-worker',password='test-pass-very-long-123')
        client = APIClient()
        tokens = client.post('/api/auth/login/',{'username':user.username,'password':'test-pass-very-long-123'},format='json').data
        tokens['access']='expired-token'
        with TemporaryDirectory() as directory:
            token_path=Path(directory)/'tokens.json'
            token_path.write_text(json.dumps(tokens))
            sender=BatchSender(self.live_server_url+'/api/v1/activity','',str(Path(directory)/'spool.jsonl'),token_file=str(token_path))
            now=timezone.now().replace(microsecond=0)
            batch={'schema_version':'1.0','agent_version':'0.1.0','employee_id':user.username,'device_id':'live-test',
                'period_start':(now-timedelta(seconds=60)).isoformat(),'period_end':now.isoformat(),
                'active_seconds':40,'idle_seconds':20,'keyboard_events':1,'mouse_events':2,
                'apps':[{'name':'Code','seconds':40}]}
            self.assertEqual(sender.send(batch),(1,0))
            self.assertEqual(sender.send(batch),(1,0))
            self.assertEqual(ComputerActivity.objects.filter(employee=user).count(),2)
            tokens=json.loads(token_path.read_text());tokens['access']='expired-again';token_path.write_text(json.dumps(tokens))
            camera=CameraEventUploader(self.live_server_url,str(token_path),str(Path(directory)/'device.json'),str(Path(directory)/'camera.json'))
            try:
                camera.log('WORKING',30,now)
                self.assertTrue(camera.flush(3))
            finally:
                camera.close()
            client.force_authenticate(user)
            report=client.get('/api/scores/dashboard/',{'date':timezone.localdate(now).isoformat()})
            self.assertEqual(report.data['applications'][0]['seconds'],40)
            self.assertEqual(report.data['camera'][0]['seconds'],30)

    def test_real_agent_logout_revokes_saved_refresh(self):
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.core.cache import cache
        cache.clear()
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from agent.main import ApiClient
        user=User.objects.create_user('logout-worker',password='test-pass-very-long-123')
        client=APIClient()
        tokens=client.post('/api/auth/login/',{'username':user.username,'password':'test-pass-very-long-123'},format='json').data
        with TemporaryDirectory() as directory:
            path=Path(directory)/'tokens.json'
            path.write_text(json.dumps(tokens))
            ApiClient(self.live_server_url,path).logout()
            self.assertFalse(path.exists())
        self.assertEqual(client.post('/api/auth/refresh/',{'refresh':tokens['refresh']},format='json').status_code,401)

    def test_primary_agent_offline_queue_recovers_against_real_django(self):
        import json
        import socket
        import sys
        import threading
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.core.cache import cache
        cache.clear()
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from agent.main import ApiClient, PendingUploader, AgentError
        user=User.objects.create_user('offline-worker',password='test-pass-very-long-123')
        client=APIClient()
        tokens=client.post('/api/auth/login/',{'username':user.username,'password':'test-pass-very-long-123'},format='json').data
        # Allocate then close a local endpoint so the first HTTP request gets
        # a real connection-refused error (a bound non-listening port can time out on macOS).
        failed,uploaded=threading.Event(),threading.Event()
        with TemporaryDirectory() as directory, socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1',0))
            token_path=Path(directory)/'tokens.json'
            queue_path=Path(directory)/'queue.json'
            token_path.write_text(json.dumps(tokens))
            unavailable_port=unavailable.getsockname()[1]
            unavailable.close()
            http=ApiClient(f'http://127.0.0.1:{unavailable_port}',token_path)
            class ObservedClient:
                def ingest(self,payload):
                    try:
                        http.ingest(payload)
                    except AgentError:
                        failed.set()
                        raise
                    uploaded.set()
            uploader=PendingUploader(ObservedClient(),queue_path)
            start=timezone.now()-timedelta(seconds=60)
            payload={'started_at':start.isoformat(),'duration_seconds':30,'application':'Code','category':'WORK'}
            uploader.append(payload)
            uploader.start()
            try:
                self.assertTrue(failed.wait(timeout=3))
                self.assertEqual(json.loads(queue_path.read_text()),[payload])
                http.api_url=self.live_server_url
                uploader.request_flush()
                self.assertTrue(uploaded.wait(timeout=3))
            finally:
                uploader.stop()
            self.assertEqual(json.loads(queue_path.read_text()),[])
            self.assertEqual(ComputerActivity.objects.filter(employee=user).count(),1)
            # Replaying the acknowledged event must not double time totals.
            http.ingest(payload)
            self.assertEqual(ComputerActivity.objects.filter(employee=user).count(),1)
            client.force_authenticate(user)
            report=client.get('/api/scores/dashboard/',{'date':timezone.localdate(start).isoformat()})
            self.assertEqual(report.data['applications'][0]['seconds'],30)


class ActiveTaskAssigneeTests(TestCase):
    def test_inactive_user_cannot_receive_new_or_reassigned_task(self):
        admin=User.objects.create_user('assignment-admin',role='ADMIN')
        active=User.objects.create_user('active-assignee')
        inactive=User.objects.create_user('inactive-assignee',is_active=False)
        client=APIClient();client.force_authenticate(admin)
        response=client.post('/api/tasks/',{'employee':inactive.pk,'title':'Invalid assignment'},format='json')
        self.assertEqual(response.status_code,400)
        task=Task.objects.create(employee=active,title='Existing')
        self.assertEqual(client.patch(f'/api/tasks/{task.pk}/',{'employee':inactive.pk},format='json').status_code,400)
        historical=Task.objects.create(employee=inactive,title='Historical')
        self.assertEqual(client.patch(f'/api/tasks/{historical.pk}/',{'status':'DONE','quality_score':80},format='json').status_code,200)
