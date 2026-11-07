from datetime import timedelta
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from activity.models import ComputerActivity
from workforce.models import Task
from .models import AuditEntry, ConsentRecord, Device, User


class SelfServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password='Before-worktrack-924!'
        self.user=User.objects.create_user('self-service',password=self.password)
        self.other=User.objects.create_user('other-service')
        self.client=APIClient()
        self.refresh=RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+str(self.refresh.access_token))

    def test_password_change_requires_old_password_and_revokes_existing_tokens(self):
        second=RefreshToken.for_user(self.user)
        payload={'current_password':'wrong','new_password':'After-worktrack-528!','confirm_password':'After-worktrack-528!'}
        self.assertEqual(self.client.post('/api/me/password/',payload,format='json').status_code,400)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(self.password))
        payload['current_password']=self.password
        self.assertEqual(self.client.post('/api/me/password/',payload,format='json').status_code,200)
        self.assertEqual(self.client.get('/api/users/me/').status_code,401)
        for token in (self.refresh,second):
            self.assertEqual(APIClient().post('/api/auth/refresh/',{'refresh':str(token)},format='json').status_code,401)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password(payload['new_password']))
        self.assertEqual(AuditEntry.objects.get().changes,{})

    def test_password_validation_and_self_scope(self):
        base={'current_password':self.password,'new_password':'12345678','confirm_password':'12345678'}
        for change in ({},{'new_password':'Strong-new-479!'}, {'user_id':self.other.pk}, {'new_password':self.password,'confirm_password':self.password}):
            self.assertEqual(self.client.post('/api/me/password/',{**base,**change},format='json').status_code,400)
        self.assertFalse(AuditEntry.objects.exists())

    def test_link_requires_consent_and_mints_separate_agent_session_for_self(self):
        payload={'name':'QA laptop','platform':'Test','consent':False,'policy_version':'2026-11'}
        self.assertEqual(self.client.post('/api/desktop/link/',payload,format='json').status_code,400)
        self.assertFalse(Device.objects.exists());self.assertFalse(ConsentRecord.objects.exists())
        payload['consent']=True
        result=self.client.post('/api/desktop/link/',payload,format='json')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result['Cache-Control'],'no-store')
        self.assertNotEqual(result.data['refresh'],str(self.refresh))
        self.assertEqual(Device.objects.get().employee,self.user)
        self.assertEqual(ConsentRecord.objects.get().employee,self.user)
        agent=APIClient();agent.credentials(HTTP_AUTHORIZATION='Bearer '+result.data['access'])
        self.client.post('/api/auth/logout/',{'refresh':str(self.refresh)},format='json')
        self.assertEqual(agent.get('/api/users/me/').data['id'],self.user.pk)
        self.assertEqual(self.client.post('/api/desktop/link/',{**payload,'user_id':self.other.pk},format='json').status_code,400)

    def test_today_is_self_only_even_for_admin_and_ignores_foreign_query_id(self):
        self.user.role='ADMIN';self.user.save()
        now=timezone.now()-timedelta(seconds=90)
        for user,seconds,title in ((self.user,30,'My task'),(self.other,60,'Private foreign task')):
            ComputerActivity.objects.create(employee=user,started_at=now,duration_seconds=seconds,application=title)
            Task.objects.create(employee=user,title=title,due_date=timezone.localdate()-timedelta(days=1))
        response=self.client.get('/api/me/today/',{'employee_id':self.other.pk})
        self.assertEqual(response.data['tracked_seconds'],30)
        self.assertEqual(response.data['open_tasks'],1)
        self.assertNotIn('Private foreign task',str(response.data))

    def test_self_service_requires_authentication(self):
        client=APIClient()
        self.assertEqual(client.get('/api/me/today/').status_code,401)
        for path in ('/api/me/password/','/api/desktop/link/'):
            self.assertEqual(client.post(path,{},format='json').status_code,401)
