#!/usr/bin/env python3
"""Interactive local launcher for the WorkTrack web app and monitoring agent."""
import argparse
import errno
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
API = 'http://127.0.0.1:8000'
WEB = 'http://127.0.0.1:5173'
RUNTIME = ROOT / '.runtime'


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
    expected=source_digest(ROOT/'backend')
    try:
        with urlopen(API+'/api/health/',timeout=3) as response:
            data=json.load(response)
    except HTTPError as exc:
        exc.close()
        raise RuntimeError('8000 порт дээр backend байгаа боловч health/version шалгалт амжилтгүй. Хуучин backend/launcher цонхыг Ctrl+C-ээр зогсоогоод дахин асаана уу.') from exc
    except URLError as exc:
        if isinstance(exc.reason, ConnectionRefusedError) or getattr(exc.reason, 'errno', None) == errno.ECONNREFUSED:
            return False
        raise RuntimeError('Backend порт хариу өгөхгүй байна. Хоёр дахь сервер асаахгүй; өмнөх process болон логийг шалгана уу.') from exc
    except (TimeoutError,OSError) as exc:
        if isinstance(exc, ConnectionRefusedError) or getattr(exc, 'errno', None) == errno.ECONNREFUSED:
            return False
        raise RuntimeError('Backend шалгалтын timeout/сүлжээний алдаа. Өмнөх process-ийг шалгана уу.') from exc
    except (ValueError,TypeError) as exc:
        raise RuntimeError('8000 порт дээр танигдаагүй сервер байна. Өөр process-ийг автоматаар зогсоохгүй.') from exc
    if not isinstance(data,dict) or data.get('service')!='worktrack-api' or data.get('protocol')!=1 or data.get('source_digest')!=expected or data.get('workspace_id')!=workspace_id(ROOT/'backend'):
        raise RuntimeError('Ажиллаж буй backend хуучин эсвэл өөр project-ийнх байна. Тэр backend/launcher цонхыг Ctrl+C-ээр зогсоогоод Start WorkTrack.command-ийг дахин нээнэ үү.')
    return True


def wait_ready(url, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'Сервер ассангүй (exit {process.returncode}). .runtime дахь log-ийг шалгана уу.')
        if check_http(url):
            return
        time.sleep(.25)
    raise RuntimeError(f'{url} асах хугацаа хэтэрлээ. .runtime дахь log-ийг шалгана уу.')


def bootstrap():
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Python virtual environment үүсгэж байна…', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    probe = subprocess.run([str(python), '-c', 'import django, rest_framework, corsheaders, dotenv, rest_framework_simplejwt; from zoneinfo import ZoneInfo; ZoneInfo("Asia/Ulaanbaatar")'], capture_output=True)
    if probe.returncode:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.txt'], cwd=ROOT, check=True)
    npm = shutil.which('npm')
    if not npm:
        raise RuntimeError('Node.js/npm суулгаад Start WorkTrack.command-ийг дахин нээнэ үү.')
    if not (ROOT / 'node_modules/vite/bin/vite.js').exists():
        subprocess.run([npm, 'ci', '--include=dev'], cwd=ROOT, check=True)
    env = ROOT / 'backend/.env'
    if not env.exists():
        sample = (ROOT / 'backend/.env.example').read_text()
        env.write_text(sample.replace('replace-with-a-long-random-secret', secrets.token_urlsafe(48)))
        env.chmod(0o600)
    subprocess.run([str(python), 'manage.py', 'migrate', '--noinput'], cwd=ROOT, check=True)
    probe = subprocess.run([str(python), 'manage.py', 'shell', '-c',
        'from django.contrib.auth import get_user_model; print(get_user_model().objects.filter(is_active=True,is_superuser=True).exists())'],
        cwd=ROOT, capture_output=True, text=True, check=True)
    if probe.stdout.strip().splitlines()[-1] != 'True':
        print('Эхний admin account үүсгэнэ үү. Нууц үг бичихэд дэлгэц дээр харагдахгүй.', flush=True)
        subprocess.run([str(python), 'manage.py', 'createsuperuser'], cwd=ROOT, check=True)
    return python, npm


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
        print('Agent нь идэвхтэй аппын нэр, ашигласан хугацаа, idle хугацааг бүртгэнэ.\nТекст, цонхны гарчиг, URL, screenshot бүртгэхгүй.')
        if input('Хугацаа бүртгэхийг зөвшөөрөх үү? [y/N]: ').strip().lower() not in {'y', 'yes', 'тийм'}:
            print('Agent асаагүй. Веб систем хэвийн ажиллана.')
            return False
        client.grant_consent('2026-11')
    from agent.main import is_paused
    if is_paused():
        print('Agent pause төлөвтэй байна. Өмнөх pause сонголтыг хэвээр хадгаллаа.')
    print(f"Agent account: {config['username']}")
    return True


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            if os.name == 'nt':
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main():
    parser = argparse.ArgumentParser(description='WorkTrack: backend + frontend + agent нэг дор асаах')
    parser.add_argument('--web-only', action='store_true', help='Backend/frontend болон онооны scheduler асаах; agent/camera асаахгүй')
    parser.add_argument('--camera', action='store_true', help='Camera monitor мөн асаах')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, interrupted)
    os.chdir(ROOT)
    RUNTIME.mkdir(exist_ok=True)
    # Prevent repeated double clicks from starting duplicate collectors.
    lock = (RUNTIME / 'launcher.lock').open('a+')
    if os.name != 'nt':
        import fcntl
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('WorkTrack launcher аль хэдийн ажиллаж байна.')
            if backend_is_current():
                webbrowser.open(WEB)
            else:
                print('Backend асаж дуустал хүлээнэ үү.')
            return
    processes, logs = [], []

    def start(name, command):
        log = (RUNTIME / f'{name}.log').open('a')
        logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != 'nt')
        processes.append((name, process))
        return process

    try:
        existing_backend = backend_is_current()  # Refuse stale servers before running migrations.
        python, npm = bootstrap()
        if not existing_backend:
            wait_ready(API + '/api/health/', start('backend', [str(python), 'manage.py', 'runserver', '127.0.0.1:8000', '--noreload']))
            if not backend_is_current():
                raise RuntimeError('Backend readiness/version шалгалт амжилтгүй.')
        if not check_http(WEB):
            wait_ready(WEB, start('frontend', [npm, 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort']))
        start('scheduler', [str(python), '-u', 'manage.py', 'run_score_scheduler'])
        start('backup', [str(python), '-u', 'manage.py', 'run_backup_scheduler'])
        if not args.web_only:
            if setup_agent():
                start('agent', [str(python), '-u', 'agent/main.py'])
                camera = args.camera or input('Camera мөн асаах уу? [y/N]: ').strip().lower() in {'y', 'yes', 'тийм'}
                if camera:
                    probe = subprocess.run([str(python), '-c', 'import cv2, yaml, ultralytics'], capture_output=True)
                    if probe.returncode:
                        print('Camera dependency-уудыг суулгаж байна…', flush=True)
                        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'requirements.txt'], cwd=ROOT, check=True)
                    start('camera', [str(python), '-u', 'main.py'])
        print(f'\nWorkTrack: {WEB}\nЗогсоох: энэ цонхонд Ctrl+C. Оноо автоматаар 60 секунд тутам шинэчлэгдэнэ.\nLog: .runtime/\nЦонхоо нээлттэй байлгана уу.', flush=True)
        webbrowser.open(WEB)
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'{name} зогслоо. .runtime/{name}.log файлыг шалгана уу.')
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nWorkTrack-ийг зогсоож байна…')
    finally:
        for _, process in reversed(processes):
            stop_process(process)
        for log in logs:
            log.close()
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f'Алдаа: {exc}', file=sys.stderr)
        sys.exit(1)
