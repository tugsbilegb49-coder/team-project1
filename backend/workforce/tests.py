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
            camera.log('WORKING',30,now)
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
