import os
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

    @unittest.skipIf(worktrack.WINDOWS, 'POSIX process groups')
    def test_shutdown_signals_owned_group_then_waits(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        with patch.object(worktrack.os, 'killpg') as kill:
            worktrack.stop_process(process)
        kill.assert_called_once_with(1234, signal.SIGINT)
        process.wait.assert_called_once_with(timeout=5)

    @unittest.skipIf(worktrack.WINDOWS, 'POSIX process groups')
    def test_unresponsive_group_is_killed_after_grace_period(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('agent', 5), None]
        with patch.object(worktrack.os, 'killpg') as kill:
            worktrack.stop_process(process)
        self.assertEqual(kill.call_args_list[1].args, (1234, signal.SIGKILL))

    def test_windows_shutdown_sends_ctrl_break_to_own_group(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        with (
            patch.object(worktrack, 'WINDOWS', True),
            patch.object(worktrack.signal, 'CTRL_BREAK_EVENT', 1, create=True),
            patch.object(worktrack.subprocess, 'run') as run,
        ):
            worktrack.stop_process(process)
        process.send_signal.assert_called_once_with(1)
        process.wait.assert_called_once_with(timeout=5)
        run.assert_not_called()

    def test_windows_never_sends_ctrl_break_to_a_process_without_its_own_group(self):
        process = Mock(spec=subprocess.Popen, pid=1234)  # A plain Popen, not started by spawn().
        process.poll.return_value = None
        with (
            patch.object(worktrack, 'WINDOWS', True),
            patch.object(worktrack.signal, 'CTRL_BREAK_EVENT', 1, create=True),
            patch.object(worktrack.subprocess, 'run') as run,
        ):
            worktrack.stop_process(process)
        process.send_signal.assert_not_called()
        self.assertEqual(run.call_args.args[0][0], 'taskkill')

    def test_spawned_children_are_marked_as_group_leaders(self):
        with patch.object(worktrack.subprocess, 'Popen') as popen:
            process = worktrack.spawn(['python'], cwd='.')
        self.assertTrue(process.own_group)
        self.assertEqual(popen.call_args.kwargs, {'cwd': '.', **worktrack.process_group()})

    def test_windows_unresponsive_tree_is_killed_with_taskkill(self):
        for failure in (subprocess.TimeoutExpired('agent', 5), OSError('no console')):
            with self.subTest(failure=type(failure).__name__):
                process = Mock(pid=1234)
                process.poll.return_value = None
                process.wait.side_effect = [failure, None] if isinstance(failure, subprocess.TimeoutExpired) else None
                if isinstance(failure, OSError):
                    process.send_signal.side_effect = failure
                with (
                    patch.object(worktrack, 'WINDOWS', True),
                    patch.object(worktrack.signal, 'CTRL_BREAK_EVENT', 1, create=True),
                    patch.object(worktrack.subprocess, 'run') as run,
                ):
                    worktrack.stop_process(process)
                self.assertEqual(run.call_args.args[0], ['taskkill', '/PID', '1234', '/T', '/F'])
                process.kill.assert_called_once()

    def test_children_get_their_own_process_group(self):
        with patch.object(worktrack, 'WINDOWS', False):
            self.assertEqual(worktrack.process_group(), {'start_new_session': True})
        with (
            patch.object(worktrack, 'WINDOWS', True),
            patch.object(worktrack.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200, create=True),
        ):
            self.assertEqual(worktrack.process_group(), {'creationflags': 0x200})

    def test_windows_continues_in_venv_python_without_exec(self):
        with (
            patch.object(worktrack, 'WINDOWS', True),
            patch.object(
                worktrack, 'VENV_PYTHON', Mock(exists=Mock(return_value=True), __str__=lambda _: 'venv-python')
            ),
            patch.object(worktrack.sys, 'prefix', '/system/python'),
            patch.object(worktrack.sys, 'argv', ['worktrack.py', '--desktop']),
            patch.object(worktrack.signal, 'signal'),
            patch.object(worktrack.signal, 'SIGBREAK', 21, create=True),
            patch.object(worktrack.subprocess, 'call', return_value=3) as call,
            patch.object(worktrack.os, 'execv') as execv,
        ):
            with self.assertRaises(SystemExit) as stopped:
                worktrack.ensure_venv()
        self.assertEqual(stopped.exception.code, 3)
        self.assertEqual(call.call_args.args[0][0], 'venv-python')
        self.assertEqual(call.call_args.args[0][-1], '--desktop')
        execv.assert_not_called()

    def test_web_only_launcher_also_starts_and_stops_scheduler(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        # Exercise orchestration without starting servers or collecting activity.
        with TemporaryDirectory() as directory:
            process = Mock()
            process.poll.return_value = None
            with (
                patch.object(worktrack, 'RUNTIME', Path(directory)),
                patch.object(worktrack.sys, 'argv', ['worktrack.py', '--web-only']),
                patch.object(worktrack, 'use_utf8'),
                patch.object(worktrack, 'ensure_venv'),
                patch.object(worktrack, 'bootstrap', return_value=(Path('/test/python'), 'node', False)),
                patch.object(worktrack, 'check_http', return_value=True),
                patch.object(worktrack, 'backend_is_current', return_value=True),
                patch.object(worktrack.subprocess, 'Popen', return_value=process) as launch,
                patch.object(worktrack, 'setup_agent') as agent,
                patch.object(worktrack, 'open_browser'),
                patch.object(worktrack.signal, 'signal'),
                patch.object(worktrack.time, 'sleep', side_effect=KeyboardInterrupt),
                patch.object(worktrack, 'stop_process') as stop,
            ):
                worktrack.main()
            self.assertEqual(
                [call.args[0][-1] for call in launch.call_args_list], ['run_score_scheduler', 'run_backup_scheduler']
            )
            agent.assert_not_called()
            self.assertEqual(stop.call_count, 2)

    def test_first_run_opens_the_admin_setup_page_with_a_secret_the_backend_inherits(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        seen = {}

        def launch(command, **options):
            name = 'runserver' if 'runserver' in command else command[-1]
            seen[name] = os.environ.get('WORKTRACK_SETUP_TOKEN')
            return Mock(**{'poll.return_value': None})

        with TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('WORKTRACK_SETUP_TOKEN', None)
            with (
                patch.object(worktrack, 'RUNTIME', Path(directory)),
                patch.object(worktrack.sys, 'argv', ['worktrack.py', '--web-only']),
                patch.object(worktrack, 'use_utf8'),
                patch.object(worktrack, 'ensure_venv'),
                patch.object(worktrack, 'bootstrap', return_value=(Path('/test/python'), 'node', True)),
                patch.object(worktrack, 'check_http', return_value=True),
                patch.object(worktrack, 'backend_is_current', side_effect=[False, True]),
                patch.object(worktrack.subprocess, 'Popen', side_effect=launch),
                patch.object(worktrack, 'open_browser') as browser,
                patch.object(worktrack.signal, 'signal'),
                patch.object(worktrack.time, 'sleep', side_effect=KeyboardInterrupt),
                patch.object(worktrack, 'stop_process'),
            ):
                worktrack.main()
        token = seen['runserver']
        self.assertTrue(token and len(token) >= 32)
        browser.assert_called_once_with(f'{worktrack.WEB}/#setup={token}')


class BackendIdentityTests(unittest.TestCase):
    def response(self, **changes):
        from io import BytesIO
        import json

        data = {
            'status': 'ok',
            'service': 'worktrack-api',
            'protocol': 1,
            'source_digest': 'expected',
            'workspace_id': 'workspace',
        }
        data.update(changes)
        return BytesIO(json.dumps(data).encode())

    def test_matching_server_is_reused(self):
        with (
            patch('backend.config.identity.source_digest', return_value='expected'),
            patch('backend.config.identity.workspace_id', return_value='workspace'),
            patch.object(worktrack, 'urlopen', return_value=self.response()),
        ):
            self.assertTrue(worktrack.backend_is_current())

    def test_old_foreign_or_wrong_workspace_server_is_not_reused(self):
        for change in ({'source_digest': 'old'}, {'service': 'other-app'}, {'workspace_id': 'another-project'}):
            with (
                self.subTest(change=change),
                patch('backend.config.identity.source_digest', return_value='expected'),
                patch('backend.config.identity.workspace_id', return_value='workspace'),
                patch.object(worktrack, 'urlopen', return_value=self.response(**change)),
            ):
                with self.assertRaises(RuntimeError):
                    worktrack.backend_is_current()

    def test_connection_refused_means_no_running_backend(self):
        from urllib.error import URLError

        with (
            patch.object(worktrack, 'urlopen', side_effect=URLError(ConnectionRefusedError())),
            patch('backend.config.identity.source_digest', return_value='expected'),
        ):
            self.assertFalse(worktrack.backend_is_current())

    def test_timeout_is_not_mistaken_for_a_free_port(self):
        with (
            patch.object(worktrack, 'urlopen', side_effect=TimeoutError()),
            patch('backend.config.identity.source_digest', return_value='expected'),
        ):
            with self.assertRaises(RuntimeError):
                worktrack.backend_is_current()


class ModeTests(unittest.TestCase):
    def run_main(self, argv, directory, server=None, **patches):
        from pathlib import Path

        runtime = Path(directory)
        if server:
            (runtime / 'server.json').write_text('{"server": "%s"}' % server, encoding='utf-8')
        with (
            patch.object(worktrack, 'RUNTIME', runtime),
            patch.object(worktrack.sys, 'argv', ['worktrack.py', *argv]),
            patch.object(worktrack, 'use_utf8'),
            patch.object(worktrack, 'ensure_venv'),
            patch.object(worktrack.signal, 'signal'),
            patch.object(worktrack, 'run_client') as client,
            patch.object(worktrack, 'bootstrap', side_effect=KeyboardInterrupt) as solo,
            patch.object(worktrack, 'backend_is_current', return_value=False),
        ):
            worktrack.main()
        return client, solo

    def test_saved_server_or_server_flag_starts_the_team_computer(self):
        from tempfile import TemporaryDirectory

        for argv, server in ((['--desktop'], 'https://worktrack.example.mn'), (['--server', 'x.mn'], None)):
            with self.subTest(argv=argv), TemporaryDirectory() as directory:
                client, solo = self.run_main(argv, directory, server)
                client.assert_called_once()
                solo.assert_not_called()

    def test_without_a_server_or_with_local_this_computer_runs_everything(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            client, solo = self.run_main(['--desktop', '--local'], directory, 'https://worktrack.example.mn')
            client.assert_not_called()
            solo.assert_called_once()
            self.assertFalse((Path(directory) / 'server.json').exists())

    def test_office_server_listens_on_the_network_only_through_https_without_debug_pages(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        commands = []

        def launch(command, **options):
            commands.append(command)
            return Mock(**{'poll.return_value': None})

        with TemporaryDirectory() as directory, patch.dict(os.environ):
            with (
                patch.object(worktrack, 'RUNTIME', Path(directory)),
                patch.object(worktrack.sys, 'argv', ['worktrack.py', '--web-only', '--share', '--no-browser']),
                patch.object(worktrack, 'use_utf8'),
                patch.object(worktrack, 'ensure_venv'),
                patch.object(worktrack, 'bootstrap', return_value=(Path('/test/python'), 'node', False)),
                patch.object(worktrack, 'lan_addresses', return_value=['192.168.1.20']),
                patch.object(worktrack, 'check_http', return_value=True),
                patch.object(worktrack, 'backend_is_current', side_effect=[False, True]),
                patch.object(worktrack.subprocess, 'Popen', side_effect=launch),
                patch.object(worktrack.signal, 'signal'),
                patch.object(worktrack.time, 'sleep', side_effect=KeyboardInterrupt),
                patch.object(worktrack, 'stop_process'),
                patch('desktop.tls.TLSProxy') as proxy,
            ):
                worktrack.main()
                self.assertTrue((Path(directory) / 'tls' / 'server.key').exists())
            self.assertEqual(os.environ['DJANGO_DEBUG'], 'false')
            self.assertEqual(os.environ['WORKTRACK_SHARE_ADDRESSES'], 'https://192.168.1.20:8443')
            self.assertRegex(os.environ['WORKTRACK_SHARE_CODE'], r'^[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$')
            self.assertEqual(os.environ['TRUSTED_PROXY_NETWORKS'], '127.0.0.1/32')
        runserver = next(command for command in commands if 'runserver' in command)
        self.assertIn('127.0.0.1:8000', runserver)  # Django itself stays off the network.
        self.assertIn('--insecure', runserver)
        self.assertEqual(proxy.call_args.args[0], ('0.0.0.0', 8443))
        self.assertEqual(proxy.call_args.args[3], 'http://127.0.0.1:8000')
        proxy.return_value.start.assert_called_once()
        proxy.return_value.close.assert_called_once()


class ClientPackageTests(unittest.TestCase):
    def test_missing_time_zone_database_is_installed_once(self):
        from zoneinfo import ZoneInfoNotFoundError

        lookups = Mock(side_effect=[ZoneInfoNotFoundError('Asia/Ulaanbaatar'), None])
        with (
            patch('zoneinfo.ZoneInfo', lookups),
            patch.object(worktrack.subprocess, 'run') as run,
            patch.object(worktrack.importlib, 'invalidate_caches'),
        ):
            worktrack.ensure_client_packages()
        self.assertEqual(run.call_args.args[0][1:4], ['-m', 'pip', 'install'])
        self.assertEqual(lookups.call_count, 2)

    def test_nothing_is_installed_when_time_zones_work(self):
        with patch.object(worktrack.subprocess, 'run') as run:
            worktrack.ensure_client_packages()
        run.assert_not_called()
