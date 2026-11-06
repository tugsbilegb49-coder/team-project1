import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import (
    application_for_idle_state,
    category_for,
    display_name_for_windows_process,
    is_paused,
    segment_payload,
    set_paused,
)


class AgentHelpersTests(unittest.TestCase):
    def test_configured_application_is_work(self):
        self.assertEqual(category_for("Visual Studio Code", ["Visual Studio Code"]), "WORK")

    def test_browser_is_not_assumed_to_be_work(self):
        self.assertEqual(category_for("Safari", []), "BROWSER")

    def test_windows_process_name_does_not_use_a_window_title(self):
        self.assertEqual(display_name_for_windows_process("WINWORD"), "Microsoft Word")
        self.assertEqual(display_name_for_windows_process("unknown_process"), "unknown_process")

    def test_segment_keeps_application_and_duration(self):
        from datetime import datetime, timedelta, timezone

        started_at = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
        payload = segment_payload("Visual Studio Code", "WORK", started_at, started_at + timedelta(seconds=30))
        self.assertEqual(payload["application"], "Visual Studio Code")
        self.assertEqual(payload["duration_seconds"], 30)

    def test_pause_control_is_local_and_reversible(self):
        with TemporaryDirectory() as directory:
            control_file = Path(directory) / "control.json"
            self.assertFalse(is_paused(control_file))
            set_paused(True, control_file)
            self.assertTrue(is_paused(control_file))
            set_paused(False, control_file)
            self.assertFalse(is_paused(control_file))

    def test_idle_threshold_hides_foreground_application_without_reading_input(self):
        self.assertEqual(application_for_idle_state("Visual Studio Code", 301, 300), "Idle")
        self.assertEqual(application_for_idle_state("Visual Studio Code", 30, 300), "Visual Studio Code")



class SamplingTests(unittest.TestCase):
    def simulate(self, app_at, paused_at=lambda t: False, seconds=35, wall_at=lambda t: t, tick_at=lambda t: t, beginning=None):
        from unittest.mock import Mock, patch
        import main as agent
        from datetime import datetime, timedelta, timezone
        clock = [0]
        beginning = beginning or datetime(2026,11,6,tzinfo=timezone.utc)
        rows = []
        uploader = Mock()
        uploader.append.side_effect = rows.append

        def sleep(interval):
            self.assertEqual(interval, 1)
            clock[0] += interval
            if clock[0] >= seconds:
                raise KeyboardInterrupt

        config = {'interval_seconds':30,'poll_interval_seconds':1,'idle_threshold_seconds':300,
                  'productive_apps':['Code'],'device_id':'test-device'}
        with patch.object(agent,'PendingUploader',return_value=uploader), \
             patch.object(agent.time,'monotonic',side_effect=lambda:tick_at(clock[0])), \
             patch.object(agent.time,'sleep',side_effect=sleep), \
             patch.object(agent,'_now',side_effect=lambda:beginning+timedelta(seconds=wall_at(clock[0]))), \
             patch.object(agent,'foreground_application',side_effect=lambda:app_at(clock[0])), \
             patch.object(agent,'idle_seconds',return_value=0), \
             patch.object(agent,'is_paused',side_effect=lambda:paused_at(clock[0])):
            agent.run_agent(config,Mock())
        return rows,uploader

    def test_multiple_switches_before_upload_have_separate_contiguous_segments(self):
        rows,uploader=self.simulate(lambda t:'Safari' if 10 <= t < 20 else 'Code')
        self.assertEqual([r['application'] for r in rows],['Code','Safari','Code','Code'])
        self.assertEqual([r['duration_seconds'] for r in rows],[10,10,10,4])
        self.assertEqual([r['category'] for r in rows],['WORK','BROWSER','WORK','WORK'])
        self.assertTrue(all(row['device_id']=='test-device' for row in rows))
        uploader.request_flush.assert_called_once()
        uploader.stop.assert_called_once()

    def test_stable_app_seals_at_upload_boundary(self):
        rows,_=self.simulate(lambda t:'Code')
        self.assertEqual([row['duration_seconds'] for row in rows],[30,4])

    def test_paused_time_is_not_attributed_to_an_app(self):
        rows,_=self.simulate(lambda t:'Code',lambda t:5 <= t < 10,seconds=15)
        self.assertEqual([row['duration_seconds'] for row in rows],[4,4])

    def test_lookup_failure_does_not_guess_app_during_unknown_gap(self):
        from main import AgentError
        def app(t):
            if t==5:
                raise AgentError('lookup unavailable')
            return 'Code'
        rows,_=self.simulate(app,seconds=10)
        self.assertEqual([row['duration_seconds'] for row in rows],[4,3])

    def test_sleep_gap_is_skipped_even_if_monotonic_clock_pauses(self):
        rows,_=self.simulate(lambda t:'Code',seconds=10,wall_at=lambda t:t if t<5 else t+3600)
        self.assertEqual([row['duration_seconds'] for row in rows],[4,4])

    def test_long_scheduling_gap_is_not_app_usage(self):
        jump=lambda t:t if t<5 else t+3600
        rows,_=self.simulate(lambda t:'Code',seconds=10,wall_at=jump,tick_at=jump)
        self.assertEqual(sum(row['duration_seconds'] for row in rows),8)

    def test_backward_clock_does_not_overlap_already_recorded_rows(self):
        rows,_=self.simulate(lambda t:'Code',seconds=15,wall_at=lambda t:t if t<5 else t-4)
        from datetime import datetime, timedelta
        for before,after in zip(rows,rows[1:]):
            end=datetime.fromisoformat(before['started_at'])+timedelta(seconds=before['duration_seconds'])
            self.assertLessEqual(end,datetime.fromisoformat(after['started_at']))
        self.assertEqual([row['duration_seconds'] for row in rows],[4,6])

    def test_midnight_uses_ulanbaatar_day_even_if_machine_is_utc(self):
        from datetime import datetime, timezone
        rows,_=self.simulate(lambda t:'Code',seconds=11,beginning=datetime(2026,11,6,15,59,55,tzinfo=timezone.utc))
        self.assertEqual([row['duration_seconds'] for row in rows],[5,5])
        self.assertEqual(rows[1]['started_at'],'2026-11-06T16:00:00+00:00')

    def test_duration_does_not_round_up_into_next_segment(self):
        from datetime import datetime, timedelta, timezone
        start=datetime(2026,11,6,tzinfo=timezone.utc)
        end=start+timedelta(seconds=1.06)
        self.assertEqual(segment_payload('Code','WORK',start,end)['duration_seconds'],1.06)


class UploadWorkerTests(unittest.TestCase):
    def test_slow_network_does_not_hold_sampling_queue_lock(self):
        import threading
        from unittest.mock import Mock
        from main import PendingUploader
        entered, release = threading.Event(),threading.Event()
        client=Mock()
        def ingest(row):
            entered.set()
            release.wait(timeout=2)
        client.ingest.side_effect=ingest
        with TemporaryDirectory() as directory:
            uploader=PendingUploader(client,Path(directory)/'pending.json')
            uploader.append({'application':'Code'})
            uploader.start()
            try:
                self.assertTrue(entered.wait(timeout=1))
                # A sampler can persist another segment while HTTP is blocked.
                self.assertTrue(uploader.lock.acquire(timeout=.2))
                uploader.lock.release()
                uploader.append({'application':'Safari'})
            finally:
                release.set()
                uploader.stop()
            self.assertEqual(client.ingest.call_count,2)

    def test_offline_segments_survive_restart(self):
        import json
        from unittest.mock import Mock
        from main import PendingUploader, AgentError
        client=Mock()
        client.ingest.side_effect=AgentError('offline')
        with TemporaryDirectory() as directory:
            path=Path(directory)/'pending.json'
            uploader=PendingUploader(client,path)
            uploader.append({'application':'Code'})
            uploader.start()
            uploader.stop()
            self.assertEqual(json.loads(path.read_text()),[{'application':'Code'}])
            self.assertEqual(PendingUploader(client,path).pending,[{'application':'Code'}])


class PollConfigTests(unittest.TestCase):
    def test_existing_config_defaults_to_one_second_and_rejects_invalid_poll(self):
        import json
        from main import load_config, AgentError
        with TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            config={'api_url':'http://localhost:8000','username':'worker'}
            path.write_text(json.dumps(config))
            loaded=load_config(path)
            self.assertEqual(loaded['poll_interval_seconds'],1)
            self.assertEqual(loaded['interval_seconds'],30)
            for value in (0,-1,6,True,'one',float('nan')):
                path.write_text(json.dumps({**config,'poll_interval_seconds':value}))
                with self.assertRaises(AgentError):
                    load_config(path)


class IntervalSplitTests(unittest.TestCase):
    def test_multiple_days_keep_total_and_never_exceed_hour(self):
        from datetime import datetime, timedelta, timezone
        from intervals import split_interval, REPORT_TIMEZONE
        start=datetime(2026,11,4,15,59,50,tzinfo=timezone.utc)
        end=start+timedelta(days=2,seconds=20)
        rows=list(split_interval(start,end))
        self.assertEqual(sum((b-a).total_seconds() for a,b in rows),172820)
        for a,b in rows:
            self.assertLessEqual((b-a).total_seconds(),3600)
            self.assertEqual(a.astimezone(REPORT_TIMEZONE).date(),(b-timedelta(microseconds=1)).astimezone(REPORT_TIMEZONE).date())
        self.assertTrue(all(before[1]==after[0] for before,after in zip(rows,rows[1:])))

    def test_no_empty_row_at_exact_midnight(self):
        from datetime import datetime, timedelta, timezone
        from intervals import split_interval
        midnight=datetime(2026,11,5,16,tzinfo=timezone.utc)
        self.assertEqual(len(list(split_interval(midnight-timedelta(seconds=10),midnight))),1)
        self.assertEqual(list(split_interval(midnight,midnight)),[])

    def test_camera_uploader_splits_midnight_and_long_segments(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch
        from src.api_logger import CameraEventUploader
        with TemporaryDirectory() as directory:
            uploader=CameraEventUploader('http://localhost:8000',str(Path(directory)/'tokens.json'),
                str(Path(directory)/'device.json'),str(Path(directory)/'queue.json'))
            end=datetime(2026,11,5,16,0,10,tzinfo=timezone.utc)
            with patch.object(uploader,'_send') as send:
                uploader.log('WORKING',20,end)
                self.assertEqual([call.args[0]['duration_seconds'] for call in send.call_args_list],[10,10])
                self.assertEqual(send.call_args_list[0].args[0]['timestamp'],'2026-11-05T16:00:00+00:00')
                send.reset_mock()
                uploader.log('WORKING',7200,end+timedelta(days=1))
                self.assertEqual(sum(call.args[0]['duration_seconds'] for call in send.call_args_list),7200)
                self.assertTrue(all(call.args[0]['duration_seconds']<=3600 for call in send.call_args_list))
