"""Opt-in real-time multi-device HTTP soak; default suites skip this long test."""
import json
import os
from pathlib import Path
import resource
from tempfile import TemporaryDirectory
import time
from unittest import skipUnless

from django.db import close_old_connections
from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import ComputerActivity


@skipUnless(os.environ.get('WORKTRACK_SOAK_SECONDS'),'Run via verify_soak.py')
@override_settings(REQUIRE_MONITORING_CONSENT=False)
class MultiDeviceSoakTests(LiveServerTestCase):
    def test_multi_device_http_lifecycle(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        from agent.main import ApiClient
        seconds=int(os.environ['WORKTRACK_SOAK_SECONDS'])
        devices=int(os.environ.get('WORKTRACK_SOAK_DEVICES','3'))
        with TemporaryDirectory() as directory:
            clients=[]
            for number in range(devices):
                user=User.objects.create_user(f'soak-worker-{number}')
                refresh=RefreshToken.for_user(user)
                path=Path(directory)/f'token-{number}.json'
                path.write_text(json.dumps({'access':str(refresh.access_token),'refresh':str(refresh)}))
                http=ApiClient(self.live_server_url,path)
                device=http.enroll_device('Soak workstation','synthetic-test')
                clients.append((user,http,path,device['id']))
            started=time.monotonic()
            deadline=started+seconds
            rounds=0
            latencies=[]
            while time.monotonic()<deadline:
                tick=time.monotonic()
                start=timezone.now()-timedelta(seconds=1)
                for user,http,path,device_id in clients:
                    if rounds and rounds%10==0:
                        # Exercise persisted login reuse and real JWT refresh.
                        tokens=json.loads(path.read_text())
                        tokens['access']='expired-for-soak-test'
                        path.write_text(json.dumps(tokens))
                        http=ApiClient(self.live_server_url,path)
                    payload={'started_at':start.isoformat(),'duration_seconds':1,'application':'Code' if rounds%2==0 else 'Safari',
                             'category':'WORK' if rounds%2==0 else 'BROWSER','device_id':str(device_id)}
                    before=time.monotonic()
                    http.ingest(payload)
                    latencies.append(time.monotonic()-before)
                    if rounds%5==0:
                        http.ingest(payload)  # Replay must not increase totals.
                rounds+=1
                time.sleep(max(0,min(1-(time.monotonic()-tick),deadline-time.monotonic())))
            close_old_connections()
            for user,_,_,_ in clients:
                self.assertEqual(ComputerActivity.objects.filter(employee=user).count(),rounds)
            report={'result':'passed','seconds':round(time.monotonic()-started,2),'devices':devices,'rounds':rounds,
                    'stored_segments':rounds*devices,'max_request_seconds':round(max(latencies),3),
                    'mean_request_seconds':round(sum(latencies)/len(latencies),3),
                    'max_rss_raw':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    'real_camera_or_app_capture':False,'live_database_modified':False}
            runtime=Path(__file__).resolve().parents[2]/'.runtime'
            runtime.mkdir(exist_ok=True)
            (runtime/'soak-report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report),flush=True)
