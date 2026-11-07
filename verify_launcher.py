#!/usr/bin/env python3
"""Start the real launcher the way Start WorkTrack.bat/.command does (desktop mode) and stop it
the way a person does, against a throwaway database.

Checks that a first run bootstraps .venv/node_modules, that backend, frontend and the local
desktop control come up, that a second launch does not start a second copy, that Ctrl+C
(Ctrl+Break on Windows) shuts everything down, and that no server is left running afterwards.
With --agent it also links this machine, starts the activity agent from the web API and stops
it, which proves the agent receives the stop signal and saves its last segment.

Runs in CI on Windows; also works on macOS/Linux. It refuses to run in a folder that already
has a linked device or launcher history, because it would replace them: use a clean checkout.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WINDOWS = os.name == 'nt'
API, WEB, DESKTOP = 'http://127.0.0.1:8000', 'http://127.0.0.1:5173', 'http://127.0.0.1:8766'
PORTS = {'backend': 8000, 'frontend': 5173, 'desktop control': 8766}
LOCAL_STATE = ('.runtime/desktop-session.json', '.runtime/launcher-usage.sqlite3', 'agent/.agent_tokens.json')


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(0.5)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def request(url, data=None, headers=None):
    """Return (status, parsed JSON or None) without raising for HTTP error codes."""
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urlopen(Request(url, data=body, headers=headers or {}), timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read()
        error.close()
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, None
    except (URLError, OSError, ValueError):
        return None, None


def wait_for(description, condition, launcher, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if launcher is not None and launcher.poll() is not None:
            raise AssertionError(f'Launcher exited with {launcher.returncode} while waiting for {description}.')
        if condition():
            return
        time.sleep(1)
    raise AssertionError(f'Timed out after {timeout}s waiting for {description}.')


def group_options():
    if WINDOWS:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def interrupt(process):
    """What pressing Ctrl+C in the launcher window does."""
    if WINDOWS:
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.killpg(process.pid, signal.SIGINT)


def kill_tree(process):
    if process.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=30)


def descendants(pid):
    """The launcher's child processes, or None when psutil is not installed."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        return psutil.Process(pid).children(recursive=True)
    except psutil.Error:
        return []


def still_running(process):
    import psutil

    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def exercise_agent(env):
    """Link this machine, start the agent from the web API and stop it again."""
    status, tokens = request(
        API + '/api/auth/login/',
        {'username': env['DJANGO_SUPERUSER_USERNAME'], 'password': env['DJANGO_SUPERUSER_PASSWORD']},
        {'Content-Type': 'application/json'},
    )
    assert status == 200 and tokens and tokens.get('access'), f'Login failed: {status} {tokens}'
    headers = {
        'Authorization': 'Bearer ' + tokens['access'],
        'X-WorkTrack-Desktop': '1',
        'Origin': WEB,
        'Content-Type': 'application/json',
    }

    def act(action, data=None):
        status, state = request(f'{DESKTOP}/desktop/{action}/', data if data is not None else {}, headers)
        assert status == 200, f'/desktop/{action}/ returned {status}: {state}'
        return state

    state = act('connect', {'device_name': 'Launcher smoke тест', 'consent': True})
    assert state['linked'] and state['device_name'] == 'Launcher smoke тест', state
    log = ROOT / '.runtime/agent.log'
    offset = log.stat().st_size if log.exists() else 0
    state = act('start')
    assert state['computer_running'], f'Agent did not start: {state}'
    time.sleep(5)  # Let it sample a few times; on a headless runner the lookup may fail, which is fine.
    _, state = request(DESKTOP + '/desktop/status/', headers={k: v for k, v in headers.items() if k != 'Origin'})
    assert state and state['computer_running'], f'Agent stopped by itself: {state}'
    state = act('stop')
    assert not state['computer_running'], state
    with log.open(encoding='utf-8', errors='replace') as stream:
        stream.seek(offset)
        output = stream.read()
    # run_agent prints this only from its finally block, i.e. after a graceful stop.
    assert 'Desktop agent stopped.' in output, 'Agent was killed instead of stopping cleanly:\n' + output[-3000:]
    print('PASSED: agent started from the web and stopped cleanly', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--agent', action='store_true', help='Also link this machine and start/stop the agent.')
    parser.add_argument('--timeout', type=int, default=900, help='Seconds allowed for the first-run bootstrap.')
    args = parser.parse_args()
    existing = [name for name in LOCAL_STATE if (ROOT / name).exists()]
    if existing:
        raise SystemExit(f'Refusing to run: {", ".join(existing)} exists. Use a clean checkout (or CI).')
    busy = [name for name, port in PORTS.items() if port_open(port)]
    if busy:
        raise SystemExit(f'Close WorkTrack first; already in use: {", ".join(busy)}.')

    with tempfile.TemporaryDirectory(prefix='worktrack-launcher-', ignore_cleanup_errors=True) as directory:
        directory = Path(directory)
        (directory / 'launcher_smoke_settings.py').write_text(
            'from pathlib import Path\n'
            'from config.settings import *  # noqa: F403\n'
            f'BASE_DIR = Path({str(directory)!r})  # backups go here\n'
            'DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", '
            f'"NAME": {str(directory / "db.sqlite3")!r}}}}}\n',
            encoding='utf-8',
        )
        env = {
            **os.environ,
            'DJANGO_SETTINGS_MODULE': 'launcher_smoke_settings',
            'PYTHONPATH': os.pathsep.join([str(directory), str(ROOT / 'backend')]),
            'DJANGO_SUPERUSER_USERNAME': 'launcher-smoke',
            'DJANGO_SUPERUSER_EMAIL': 'launcher-smoke@example.invalid',
            'DJANGO_SUPERUSER_PASSWORD': secrets.token_urlsafe(24),
        }
        # Desktop mode refuses to start without an admin; create one in the throwaway database.
        for command in (['migrate', '--noinput'], ['createsuperuser', '--noinput']):
            subprocess.run(
                [sys.executable, 'manage.py', *command], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL
            )

        command = [sys.executable, 'worktrack.py', '--desktop', '--no-browser']
        log_path = directory / 'launcher.log'
        failed = True
        with log_path.open('wb') as log:
            launcher = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **group_options(),
            )
            try:
                started = time.monotonic()
                wait_for(
                    'backend, frontend and desktop control',
                    lambda: (
                        request(API + '/api/health/')[0] == 200
                        and request(WEB)[0] == 200
                        and request(DESKTOP + '/desktop/status/', headers={'X-WorkTrack-Desktop': '1'})[0] == 401
                    ),
                    launcher,
                    args.timeout,
                )
                print(f'PASSED: launcher started in {time.monotonic() - started:.0f}s', flush=True)

                second = subprocess.run(
                    command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=180
                )
                output = second.stdout.decode('utf-8', 'replace') + second.stderr.decode('utf-8', 'replace')
                assert second.returncode == 0 and 'аль хэдийн ажиллаж байна' in output, (
                    f'A second launch was not refused cleanly (exit {second.returncode}):\n{output}'
                )
                print('PASSED: second launch reused the running copy', flush=True)

                if args.agent:
                    exercise_agent(env)

                children = descendants(launcher.pid)
                interrupt(launcher)
                code = launcher.wait(timeout=120)
                assert code == 0, f'Launcher exited with {code} after Ctrl+C.'
                wait_for('all ports to close', lambda: not any(port_open(port) for port in PORTS.values()), None, 30)
                if children is not None:
                    alive = [child.pid for child in children if still_running(child)]
                    assert not alive, f'Processes left running after Ctrl+C: {alive}'
                print('PASSED: Ctrl+C stopped every process and freed the ports', flush=True)
                failed = False
            except AssertionError as error:
                print(f'FAILED: {error}', flush=True)
            finally:
                kill_tree(launcher)
        output = log_path.read_text(encoding='utf-8', errors='replace')
        if not failed and 'WorkTrack-ийг зогсоож байна' not in output:
            print('FAILED: the launcher did not report a clean shutdown.', flush=True)
            failed = True
        if failed:
            print('Launcher log:\n' + output[-6000:], flush=True)
            for name in ('backend', 'frontend', 'agent', 'scheduler', 'backup'):
                path = ROOT / '.runtime' / f'{name}.log'
                if path.exists():
                    print(f'--- .runtime/{name}.log\n' + path.read_text(encoding='utf-8', errors='replace')[-3000:])
            return 1
    print('Launcher smoke test passed.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
