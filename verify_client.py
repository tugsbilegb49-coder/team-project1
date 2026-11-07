#!/usr/bin/env python3
"""Use a team computer against a throwaway WorkTrack server, the way an employee does.

Starts a disposable Django server (temporary database), then the team computer: `python
worktrack.py` from this checkout, or an installed app given with --command, with an empty
WORKTRACK_HOME. Checks that the page asks for the server address and accepts it, that the built
web app and its API calls work through the local gateway, that the device links and the agent
starts and stops cleanly, that «WorkTrack хаах» ends every process, and that the next start
remembers the server.

Close WorkTrack before running it (it needs ports 8000, 5173 and 8766).
"""

import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

from verify_launcher import group_options, kill_tree, port_open, request, wait_for

ROOT = Path(__file__).resolve().parent
SERVER, WEB = 'http://127.0.0.1:8000', 'http://127.0.0.1:5173'
LOCAL = {'Origin': WEB, 'X-WorkTrack-Desktop': '1'}


def text(url):
    """Page body as text (the gateway serves HTML for the app and the setup page)."""
    from urllib.request import urlopen

    try:
        with urlopen(url, timeout=10) as response:
            return response.read().decode('utf-8', 'replace')
    except OSError:
        return ''


def start_client(command, env, log):
    return subprocess.Popen(
        [*command, '--desktop', '--team', '--no-browser'],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        **group_options(),
    )


def quit_client(client, headers):
    status, _ = request(WEB + '/desktop/quit/', {}, {**headers, 'Content-Type': 'application/json'})
    assert status == 200, f'«WorkTrack хаах» failed: {status}'
    assert client.wait(timeout=60) == 0, f'Client exited with {client.returncode}'
    wait_for('the client ports to close', lambda: not port_open(5173) and not port_open(8766), None, 30)


def exercise(client, command, env, home, log, password):
    wait_for('the setup page', lambda: 'Сервертэй холбох' in text(WEB + '/'), client, 900)
    status, body = request(
        WEB + '/setup/server', {'url': '127.0.0.1:8000'}, {'Origin': WEB, 'Content-Type': 'application/json'}
    )
    assert status == 200 and body == {'server': SERVER}, f'Saving the server failed: {status} {body}'
    wait_for('the local control', lambda: request(WEB + '/desktop/status/', headers=LOCAL)[0] == 401, client, 60)
    assert 'id="root"' in text(WEB + '/'), 'The built web app is not served after setup.'
    status, health = request(WEB + '/api/health/')
    assert status == 200 and health['service'] == 'worktrack-api', f'API through the gateway: {status} {health}'
    print('PASSED: setup page saved the server; web app and API work through the gateway', flush=True)

    status, tokens = request(
        WEB + '/api/auth/login/',
        {'username': 'client-smoke', 'password': password},
        {'Content-Type': 'application/json'},
    )
    assert status == 200, f'Login through the gateway failed: {status} {tokens}'
    headers = {**LOCAL, 'Authorization': 'Bearer ' + tokens['access'], 'Content-Type': 'application/json'}

    def act(action, data=None):
        status, state = request(f'{WEB}/desktop/{action}/', data if data is not None else {}, headers)
        assert status == 200, f'/desktop/{action}/ returned {status}: {state}'
        return state

    state = act('connect', {'device_name': 'Ажилтны компьютер', 'consent': True})
    assert state['linked'], state
    _, devices = request(WEB + '/api/devices/', headers={'Authorization': headers['Authorization']})
    names = [row['name'] for row in (devices.get('results', devices) if isinstance(devices, dict) else devices)]
    assert 'Ажилтны компьютер' in names, f'The server does not list the device: {devices}'
    agent_log = home / '.runtime' / 'agent.log'
    state = act('start')
    assert state['computer_running'], f'Agent did not start: {state}'
    time.sleep(5)
    state = act('stop')
    assert not state['computer_running'], state
    output = agent_log.read_text(encoding='utf-8', errors='replace') if agent_log.exists() else ''
    assert 'Desktop agent stopped.' in output, 'Agent was killed instead of stopping cleanly:\n' + output[-3000:]
    print('PASSED: device linked on the server; agent started and stopped cleanly', flush=True)

    quit_client(client, headers)
    print('PASSED: «WorkTrack хаах» ended every process', flush=True)
    again = start_client(command, env, log)
    try:
        wait_for('the remembered server', lambda: 'id="root"' in text(WEB + '/'), again, 120)
        wait_for('the local control', lambda: request(WEB + '/desktop/status/', headers=LOCAL)[0] == 401, again, 60)
        quit_client(again, headers)
    finally:
        kill_tree(again)
    print('PASSED: the next start went straight to the app', flush=True)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--command', help='Installed app to test, e.g. dist/WorkTrack/WorkTrack.exe')
    args = parser.parse_args()
    busy = [port for port in (8000, 5173, 8766) if port_open(port)]
    if busy:
        raise SystemExit(f'Close WorkTrack first; ports in use: {busy}.')
    command = [args.command] if args.command else [sys.executable, str(ROOT / 'worktrack.py')]

    with tempfile.TemporaryDirectory(prefix='worktrack-client-', ignore_cleanup_errors=True) as directory:
        directory = Path(directory)
        home = directory / 'home'
        (directory / 'client_smoke_settings.py').write_text(
            'from pathlib import Path\n'
            'from config.settings import *  # noqa: F403\n'
            f'BASE_DIR = Path({str(directory)!r})\n'
            'DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "OPTIONS": SQLITE_OPTIONS, '  # noqa: F405
            f'"NAME": {str(directory / "db.sqlite3")!r}}}}}\n',
            encoding='utf-8',
        )
        password = secrets.token_urlsafe(24)
        server_env = {
            **os.environ,
            'DJANGO_SETTINGS_MODULE': 'client_smoke_settings',
            'PYTHONPATH': os.pathsep.join([str(directory), str(ROOT / 'backend')]),
            'DJANGO_SUPERUSER_USERNAME': 'client-smoke',
            'DJANGO_SUPERUSER_EMAIL': 'client-smoke@example.invalid',
            'DJANGO_SUPERUSER_PASSWORD': password,
        }
        for step in (['migrate', '--noinput'], ['createsuperuser', '--noinput']):
            subprocess.run(
                [sys.executable, 'manage.py', *step], cwd=ROOT, env=server_env, check=True, stdout=subprocess.DEVNULL
            )
        client_env = {key: value for key, value in os.environ.items() if not key.startswith('DJANGO_')}
        # A team computer never runs Django. If it ever tried, this makes it fail at once instead of
        # touching the checkout's real database.
        client_env.update(
            WORKTRACK_HOME=str(home), PYTHONUTF8='1', DJANGO_SETTINGS_MODULE='team_computer_must_not_run_django'
        )
        failed = True
        with (directory / 'server.log').open('wb') as server_log, (directory / 'client.log').open('wb') as log:
            server = subprocess.Popen(
                [sys.executable, 'manage.py', 'runserver', '127.0.0.1:8000', '--noreload'],
                cwd=ROOT,
                env=server_env,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                **group_options(),
            )
            client = None
            try:
                wait_for('the server', lambda: request(SERVER + '/api/health/')[0] == 200, server, 60)
                client = start_client(command, client_env, log)
                exercise(client, command, client_env, home, log, password)
                failed = False
            except AssertionError as error:
                print(f'FAILED: {error}', flush=True)
            finally:
                if client:
                    kill_tree(client)
                kill_tree(server)
        if failed:
            print(
                '--- client output\n' + (directory / 'client.log').read_text(encoding='utf-8', errors='replace')[-4000:]
            )
            for path in sorted((home / '.runtime').glob('*.log')):
                print(f'--- {path.name}\n' + path.read_text(encoding='utf-8', errors='replace')[-2500:])
            print('--- server\n' + (directory / 'server.log').read_text(encoding='utf-8', errors='replace')[-2500:])
            return 1
    print('Team computer smoke test passed.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
