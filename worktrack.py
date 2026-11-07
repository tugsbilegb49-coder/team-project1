#!/usr/bin/env python3
"""Interactive local launcher for the WorkTrack web app and monitoring agent."""

import argparse
from contextlib import ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

if sys.version_info < (3, 10):
    sys.exit('WorkTrack-д Python 3.10 буюу шинэ хувилбар хэрэгтэй (3.12 зөвлөнө): https://www.python.org/downloads/')

ROOT = Path(__file__).resolve().parent
API = 'http://127.0.0.1:8000'
WEB = 'http://127.0.0.1:5173'
RUNTIME = ROOT / '.runtime'
WINDOWS = os.name == 'nt'
VENV_PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if WINDOWS else 'bin/python')
LAUNCHER = 'Start WorkTrack.bat' if WINDOWS else 'Start WorkTrack.command'


def use_utf8():
    """Keep Cyrillic output working on Windows code pages (cp1252/cp866) and in log files."""
    os.environ.setdefault('PYTHONUTF8', '1')  # Every child process inherits UTF-8 mode.
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or '').lower().replace('-', '') != 'utf8':
                stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def process_group():
    """Popen options giving a child its own process group, so stop_process can stop it with its children."""
    if WINDOWS:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def spawn(command, **options):
    """Start a child in its own process group; stop it later with stop_process."""
    process = subprocess.Popen(command, **options, **process_group())
    process.own_group = True
    return process


def ensure_venv():
    """Create .venv on the first run and continue the launcher with its Python."""
    if not VENV_PYTHON.exists():
        print('Python virtual environment үүсгэж байна…', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    if Path(sys.prefix).resolve() == (ROOT / '.venv').resolve():
        return
    command = [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]]
    if not WINDOWS:
        os.execv(command[0], command)
    # Windows has no exec. Run the venv launcher in this console; it handles Ctrl+C/Ctrl+Break
    # itself, while this process only waits and passes its exit code on.
    for name in ('SIGINT', 'SIGBREAK'):
        signal.signal(getattr(signal, name), signal.SIG_IGN)
    raise SystemExit(subprocess.call(command))


def open_browser():
    if sys.platform == 'darwin':
        try:
            subprocess.run(['/usr/bin/open', WEB], timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            print(f'Browser-оос {WEB} нээнэ үү.', flush=True)
    else:
        webbrowser.open(WEB)


def check_http(url):
    try:
        with urlopen(url, timeout=1) as response:
            return response.status == 200
    except HTTPError as exc:
        return exc.code == 401 and exc.headers.get('Content-Type', '').startswith('application/json')
    except (URLError, TimeoutError, OSError):
        return False


def backend_is_current():
    from backend.config.identity import source_digest, workspace_id

    expected = source_digest(ROOT / 'backend')
    try:
        with urlopen(API + '/api/health/', timeout=3) as response:
            data = json.load(response)
    except HTTPError as exc:
        exc.close()
        raise RuntimeError(
            '8000 порт дээр backend байгаа боловч health/version шалгалт амжилтгүй. Хуучин backend/launcher цонхыг Ctrl+C-ээр зогсоогоод дахин асаана уу.'
        ) from exc
    except URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError) or getattr(exc.reason, 'errno', None) == errno.ECONNREFUSED:
            return False
        raise RuntimeError(
            'Backend порт хариу өгөхгүй байна. Хоёр дахь сервер асаахгүй; өмнөх process болон логийг шалгана уу.'
        ) from exc
    except (TimeoutError, OSError) as exc:
        if isinstance(exc, ConnectionRefusedError) or getattr(exc, 'errno', None) == errno.ECONNREFUSED:
            return False
        raise RuntimeError('Backend шалгалтын timeout/сүлжээний алдаа. Өмнөх process-ийг шалгана уу.') from exc
    except (ValueError, TypeError) as exc:
        raise RuntimeError('8000 порт дээр танигдаагүй сервер байна. Өөр process-ийг автоматаар зогсоохгүй.') from exc
    if (
        not isinstance(data, dict)
        or data.get('service') != 'worktrack-api'
        or data.get('protocol') != 1
        or data.get('source_digest') != expected
        or data.get('workspace_id') != workspace_id(ROOT / 'backend')
    ):
        raise RuntimeError(
            f'Ажиллаж буй backend хуучин эсвэл өөр project-ийнх байна. Тэр backend/launcher цонхыг Ctrl+C-ээр зогсоогоод {LAUNCHER}-ийг дахин нээнэ үү.'
        )
    return True


def wait_ready(url, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Сервер ассангүй (exit {process.returncode}). .runtime дахь log-ийг шалгана уу.')
        if check_http(url):
            return
        time.sleep(0.25)
    raise RuntimeError(f'{url} асах хугацаа хэтэрлээ. .runtime дахь log-ийг шалгана уу.')


def bootstrap(interactive=True):
    python = VENV_PYTHON
    state_file = RUNTIME / 'dependencies.json'
    try:
        state = json.loads(state_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}

    def digest(names):
        value = hashlib.sha256()
        for name in names:
            value.update((ROOT / name).read_bytes())
        return value.hexdigest()

    backend_digest = digest(['backend/requirements.txt'])
    probe = subprocess.run(
        [
            str(python),
            '-c',
            'import django, rest_framework, corsheaders, dotenv, rest_framework_simplejwt, psycopg, openpyxl; from zoneinfo import ZoneInfo; ZoneInfo("Asia/Ulaanbaatar")',
        ],
        capture_output=True,
    )
    if probe.returncode or state.get('backend') != backend_digest:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.txt'], cwd=ROOT, check=True)
    npm, node = shutil.which('npm'), shutil.which('node')
    if not npm or not node:
        raise RuntimeError(f'Node.js/npm суулгаад {LAUNCHER}-ийг дахин нээнэ үү.')
    frontend_digest = digest(['package.json', 'package-lock.json'])
    if not (ROOT / 'node_modules/vite/bin/vite.js').exists() or state.get('frontend') != frontend_digest:
        if check_http(WEB):
            raise RuntimeError(
                'Frontend dependency шинэчлэх шаардлагатай. Өмнөх frontend/launcher цонхыг Ctrl+C-ээр зогсоогоод дахин нээнэ үү.'
            )
        subprocess.run([npm, 'ci', '--include=dev'], cwd=ROOT, check=True)
    from agent.token_store import atomic_json_write

    atomic_json_write(state_file, {'backend': backend_digest, 'frontend': frontend_digest})
    env = ROOT / 'backend/.env'
    if not env.exists():
        sample = (ROOT / 'backend/.env.example').read_text(encoding='utf-8')
        env.write_text(sample.replace('replace-with-a-long-random-secret', secrets.token_urlsafe(48)), encoding='utf-8')
        env.chmod(0o600)
    subprocess.run([str(python), 'manage.py', 'migrate', '--noinput'], cwd=ROOT, check=True)
    probe = subprocess.run(
        [
            str(python),
            'manage.py',
            'shell',
            '-c',
            'from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_active=True,is_superuser=True).exists())',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if probe.stdout.strip().splitlines()[-1] != 'True':
        if not interactive:
            raise RuntimeError(
                f'Эхний admin үүсээгүй байна. Нэг удаа {VENV_PYTHON.relative_to(ROOT)} manage.py createsuperuser ажиллуулаад WorkTrack-аа дахин нээнэ үү.'
            )
        print('Эхний admin account үүсгэнэ үү. Нууц үг бичихэд дэлгэц дээр харагдахгүй.', flush=True)
        subprocess.run([str(python), 'manage.py', 'createsuperuser'], cwd=ROOT, check=True)
    return python, node


def setup_agent():
    from agent.main import ApiClient, AgentError, DEFAULT_CONFIG_PATH, DEFAULT_TOKEN_PATH, load_config, save_config

    if not DEFAULT_CONFIG_PATH.exists():
        shutil.copyfile(ROOT / 'agent/config.example.json', DEFAULT_CONFIG_PATH)
    config = load_config(DEFAULT_CONFIG_PATH)
    config['api_url'] = API
    client = ApiClient(API, DEFAULT_TOKEN_PATH)
    try:
        if config['username'] == 'employee_username':
            raise AgentError('Login required')
        device = client.enroll_device(platform.node() or 'WorkTrack device', platform.system())
    except AgentError:
        from getpass import getpass

        print('\nAgent аль account-д хугацаа бүртгэхийг тохируулна. Вебийн login үүнээс тусдаа.', flush=True)
        config['username'] = input('Username: ').strip()
        client.login(config['username'], getpass('Password: '))
        device = client.enroll_device(platform.node() or 'WorkTrack device', platform.system())
    # Verify the actual saved token identity, even if the config was edited.
    tokens = client._read_tokens()
    headers = {'Authorization': 'Bearer ' + tokens['access']}
    with urlopen(Request(API + '/api/users/me/', headers=headers), timeout=10) as response:
        config['username'] = json.load(response)['username']
    config['device_id'] = str(device['id'])
    save_config(DEFAULT_CONFIG_PATH, config)
    with urlopen(Request(API + '/api/consents/status/', headers=headers), timeout=10) as response:
        consent = json.load(response)
    if not consent['active']:
        print(
            'Agent нь идэвхтэй аппын нэр, ашигласан хугацаа, idle хугацааг бүртгэнэ.\nТекст, цонхны гарчиг, URL, screenshot бүртгэхгүй.'
        )
        if input('Хугацаа бүртгэхийг зөвшөөрөх үү? [y/N]: ').strip().lower() not in {'y', 'yes', 'тийм'}:
            print('Agent асаагүй. Веб систем хэвийн ажиллана.')
            return False
        client.grant_consent('2026-11')
    from agent.main import is_paused

    if is_paused():
        print('Agent pause төлөвтэй байна. Өмнөх pause сонголтыг хэвээр хадгаллаа.')
    print(f'Agent account: {config["username"]}')
    return True


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if not WINDOWS:
            os.killpg(process.pid, signal.SIGINT)
        elif getattr(process, 'own_group', False):
            # Ctrl+Break for that process group only; Python children turn it into
            # KeyboardInterrupt and save their state, like SIGINT on macOS/Linux.
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            # Windows delivers Ctrl+Break for a pid that leads no group to the whole console,
            # this launcher included, so such a process is only force-stopped.
            raise OSError('Not started by spawn(); no own process group.')
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            if WINDOWS:
                # /T also ends grandchildren, e.g. pip's build steps.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main():
    started_at = time.time()
    parser = argparse.ArgumentParser(description='WorkTrack: backend + frontend + agent нэг дор асаах')
    parser.add_argument(
        '--web-only', action='store_true', help='Backend/frontend болон онооны scheduler асаах; agent/camera асаахгүй'
    )
    parser.add_argument('--camera', action='store_true', help='Camera monitor мөн асаах')
    parser.add_argument('--desktop', action='store_true', help='Вебээс төхөөрөмж холбох, agent/camera удирдах')
    parser.add_argument('--no-browser', action='store_true', help='Browser автоматаар нээхгүй')
    parser.add_argument('--app-id', help=argparse.SUPPRESS)
    args = parser.parse_args()
    use_utf8()
    ensure_venv()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    for name in ('SIGHUP', 'SIGBREAK'):  # Terminal closed (macOS/Linux); Ctrl+Break (Windows).
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    os.chdir(ROOT)
    RUNTIME.mkdir(exist_ok=True)
    from agent.process_lock import AlreadyRunningError, collector_lock

    instance = ExitStack()
    try:
        # Prevent repeated double clicks from starting duplicate collectors.
        instance.enter_context(collector_lock('launcher', RUNTIME))
    except AlreadyRunningError:
        print('WorkTrack launcher аль хэдийн ажиллаж байна.')
        if not backend_is_current():
            print('Backend асаж дуустал хүлээнэ үү.')
        elif not args.no_browser:
            open_browser()
        return
    processes, logs = [], []
    desktop, controller, usage = None, None, None
    shutdown = threading.Event()

    def start(name, command):
        log = (RUNTIME / f'{name}.log').open('a')
        logs.append(log)
        process = spawn(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        processes.append((name, process))
        return process

    try:
        existing_backend = backend_is_current()  # Refuse stale servers before running migrations.
        python, node = bootstrap(interactive=not args.desktop)
        from desktop.usage import LauncherUsage

        usage = LauncherUsage(RUNTIME / 'launcher-usage.sqlite3')
        if args.desktop:
            os.environ.setdefault('WORKTRACK_DESKTOP_URL', 'http://127.0.0.1:8766')
            if sys.platform == 'darwin' and not (ROOT / 'WorkTrack.app').exists():
                from desktop.build_macos_app import build

                build()
        if not existing_backend:
            wait_ready(
                API + '/api/health/',
                start('backend', [str(python), 'manage.py', 'runserver', '127.0.0.1:8000', '--noreload']),
            )
            if not backend_is_current():
                raise RuntimeError('Backend readiness/version шалгалт амжилтгүй.')
        if not check_http(WEB):
            wait_ready(
                WEB,
                # Run vite with node directly: no npm/cmd.exe wrapper that could outlive a stop on Windows.
                start(
                    'frontend',
                    [node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
                ),
            )
        start('scheduler', [str(python), '-u', 'manage.py', 'run_score_scheduler'])
        start('backup', [str(python), '-u', 'manage.py', 'run_backup_scheduler'])
        if args.desktop:
            from desktop.service import DesktopController, DesktopServer

            controller = DesktopController(ROOT, API, python, shutdown.set, started_at=started_at, usage=usage)
            desktop = DesktopServer(('127.0.0.1', 8766), controller, {WEB, 'http://localhost:5173'})
            desktop.start()
        elif not args.web_only:
            if setup_agent():
                start('agent', [str(python), '-u', 'agent/main.py'])
                camera = args.camera or input('Camera мөн асаах уу? [y/N]: ').strip().lower() in {'y', 'yes', 'тийм'}
                if camera:
                    probe = subprocess.run([str(python), '-c', 'import cv2, yaml, ultralytics'], capture_output=True)
                    if probe.returncode:
                        print('Camera dependency-уудыг суулгаж байна…', flush=True)
                        subprocess.run(
                            [str(python), '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=ROOT, check=True
                        )
                    start('camera', [str(python), '-u', 'main.py', '--consent'])
        print(
            f'\nWorkTrack: {WEB}\nЗогсоох: энэ цонхонд Ctrl+C. Оноо автоматаар 60 секунд тутам шинэчлэгдэнэ.\nLog: .runtime/\nЦонхоо нээлттэй байлгана уу.',
            flush=True,
        )
        if not args.no_browser:
            open_browser()
        while not shutdown.is_set():
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'{name} зогслоо. .runtime/{name}.log файлыг шалгана уу.')
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nWorkTrack-ийг зогсоож байна…')
    finally:
        if desktop:
            desktop.close()
        if controller:
            controller.close()
        for _, process in reversed(processes):
            stop_process(process)
        for log in logs:
            log.close()
        if usage:
            usage.close()
        instance.close()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f'Алдаа: {exc}', file=sys.stderr)
        sys.exit(1)
