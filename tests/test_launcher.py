import signal
import subprocess
import unittest
from unittest.mock import Mock, patch

import worktrack


class LauncherTests(unittest.TestCase):
    def test_failed_service_stops_readiness_wait(self):
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        with self.assertRaisesRegex(RuntimeError, 'exit 1'):
            worktrack.wait_ready('http://localhost:8000', process)

    def test_running_service_is_ready(self):
        process = Mock()
        process.poll.return_value = None
        with patch.object(worktrack, 'check_http', return_value=True):
            worktrack.wait_ready('http://localhost:8000', process)

    def test_finished_process_is_not_signalled(self):
        process = Mock()
        process.poll.return_value = 0
        worktrack.stop_process(process)
        process.wait.assert_not_called()
        process.terminate.assert_not_called()

    @unittest.skipIf(worktrack.os.name == 'nt', 'POSIX process groups')
    def test_shutdown_signals_owned_group_then_waits(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        with patch.object(worktrack.os, 'killpg') as kill:
            worktrack.stop_process(process)
        kill.assert_called_once_with(1234, signal.SIGINT)
        process.wait.assert_called_once_with(timeout=5)

    @unittest.skipIf(worktrack.os.name == 'nt', 'POSIX process groups')
    def test_unresponsive_group_is_killed_after_grace_period(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('agent',5),None]
        with patch.object(worktrack.os, 'killpg') as kill:
            worktrack.stop_process(process)
        self.assertEqual(kill.call_args_list[1].args,(1234,signal.SIGKILL))

    def test_web_only_launcher_also_starts_and_stops_scheduler(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        # Exercise orchestration without starting servers or collecting activity.
        with TemporaryDirectory() as directory:
            process=Mock()
            process.poll.return_value=None
            with patch.object(worktrack,'RUNTIME',Path(directory)), \
                 patch.object(worktrack.sys,'argv',['worktrack.py','--web-only']), \
                 patch.object(worktrack,'bootstrap',return_value=(Path('/test/python'),'npm')), \
                 patch.object(worktrack,'check_http',return_value=True), \
                 patch.object(worktrack.subprocess,'Popen',return_value=process) as launch, \
                 patch.object(worktrack,'setup_agent') as agent, \
                 patch.object(worktrack.webbrowser,'open'), \
                 patch.object(worktrack.signal,'signal'), \
                 patch.object(worktrack.time,'sleep',side_effect=KeyboardInterrupt), \
                 patch.object(worktrack,'stop_process') as stop:
                worktrack.main()
            self.assertEqual([call.args[0][-1] for call in launch.call_args_list],['run_score_scheduler','run_backup_scheduler'])
            agent.assert_not_called()
            self.assertEqual(stop.call_count,2)
