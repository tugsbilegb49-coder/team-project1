from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from django.core.cache import cache
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from activity.models import CameraPresence, ComputerActivity
from users.models import AgentHeartbeat, ConsentRecord, Device, MonitoringSettings, User
from agent.main import ApiClient, PendingUploader
from agent.runtime import AgentRuntime
from agent.token_store import save_tokens
from src.api_logger import PresenceEventUploader


@override_settings(REQUIRE_MONITORING_CONSENT=True)
class QueueAccountTests(LiveServerTestCase):
    def setUp(self):
        cache.clear()
        self.a=User.objects.create_user('queue-account-a')
        self.b=User.objects.create_user('queue-account-b')
        self.da=Device.objects.create(employee=self.a,name='A',platform='test')
        self.db=Device.objects.create(employee=self.b,name='B',platform='test')
        for user in (self.a,self.b): ConsentRecord.objects.create(employee=user,granted=True,policy_version='qa-only')

    def tokens(self,user):
        refresh=RefreshToken.for_user(user)
        return {'access':str(refresh.access_token),'refresh':str(refresh)}

    def event(self,application='A',device=None):
        row={'started_at':(timezone.now()-timedelta(seconds=60)).isoformat(),'duration_seconds':10,'application':application,'category':'WORK'}
        if device: row['device_id']=str(device.pk)
        return row

    def check_switch(self,with_device):
        with TemporaryDirectory() as directory:
            root=Path(directory);tokens=root/'tokens.json';base=root/'queue.json'
            save_tokens(tokens,self.tokens(self.a))
            a=PendingUploader(ApiClient(self.live_server_url,tokens),base)
            original=self.event(device=self.da if with_device else None)
            a.append(original)
            save_tokens(tokens,self.tokens(self.b))
            try: self.assertFalse(a.flush(3))
            finally: a.stop()
            self.assertEqual(ComputerActivity.objects.count(),0)
            b=PendingUploader(ApiClient(self.live_server_url,tokens),base)
            self.assertNotEqual(a.path,b.path)
            b.append(self.event('B',self.db if with_device else None))
            try: self.assertTrue(b.flush(3))
            finally: b.stop()
            self.assertEqual(ComputerActivity.objects.filter(employee=self.b).count(),1)
            self.assertEqual(json.loads(a.path.read_text()),[original])
            save_tokens(tokens,self.tokens(self.a))
            retry=PendingUploader(ApiClient(self.live_server_url,tokens),base)
            self.assertEqual(retry.path,a.path)
            try: self.assertTrue(retry.flush(3))
            finally: retry.stop()
            self.assertEqual(ComputerActivity.objects.filter(employee=self.a).count(),1)

    def test_old_device_queue_does_not_block_a_different_account(self):
        self.check_switch(True)

    def test_device_less_queue_never_changes_employee_after_login_switch(self):
        self.check_switch(False)

    def test_real_runtime_polls_settings_and_reports_queued_then_uploaded_events(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);tokens=root/'tokens.json'
            save_tokens(tokens,self.tokens(self.a))
            client=ApiClient(self.live_server_url,tokens)
            worker=PendingUploader(client,root/'queue.json')
            worker.append(self.event(device=self.da))
            runtime=AgentRuntime(client,str(self.da.pk),worker,lambda:False)
            try:
                self.assertTrue(runtime.cycle())
                beat=AgentHeartbeat.objects.get(device=self.da)
                self.assertEqual(beat.queue_count,1)
                self.assertIsNone(beat.last_upload_at)
                settings=MonitoringSettings.objects.get()
                settings.version+=1;settings.camera_threshold=.8;settings.save()
                self.assertTrue(worker.flush(3))
                self.assertTrue(runtime.cycle())
                beat.refresh_from_db()
                self.assertEqual(beat.queue_count,0)
                self.assertIsNotNone(beat.last_upload_at)
                self.assertEqual(beat.settings_version,settings.version)
                self.assertEqual(runtime.snapshot()['camera_threshold'],.8)
            finally: worker.stop()

    def test_presence_queue_is_account_scoped_and_legacy_queue_is_not_adopted(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);tokens=root/'tokens.json';base=root/'camera.json'
            legacy={'timestamp':(timezone.now()-timedelta(seconds=10)).isoformat(),'present':True,'confidence':.8}
            base.write_text(json.dumps([legacy]))
            save_tokens(tokens,self.tokens(self.a))
            a=PresenceEventUploader(self.live_server_url,str(tokens),str(root/'device.json'),base)
            a._worker.stop()  # The current empty account queue is safe; legacy remains untouched.
            a.log(True,.8,timezone.now()-timedelta(seconds=3))
            save_tokens(tokens,self.tokens(self.b))
            b=PresenceEventUploader(self.live_server_url,str(tokens),str(root/'device.json'),base)
            try:
                self.assertTrue(b.flush(3))
                self.assertFalse(CameraPresence.objects.exists())
                b.log(False,0,timezone.now()-timedelta(seconds=1))
                self.assertTrue(b.flush(3))
            finally:
                b.close();a.close()
            self.assertEqual(CameraPresence.objects.get().employee_id,self.b.pk)
            self.assertEqual(json.loads(base.read_text()),[legacy])
            self.assertEqual(len(json.loads(a._worker.path.read_text())),1)
