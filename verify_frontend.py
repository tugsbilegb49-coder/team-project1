#!/usr/bin/env python3
"""Run a real browser/Django smoke flow in a fresh disposable database."""
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent


def free_port():
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0))
        return reserved.getsockname()[1]


def main():
    npm=shutil.which('npm')
    if not npm:
        raise SystemExit('npm is required.')
    with tempfile.TemporaryDirectory(prefix='worktrack-ui-') as directory:
        temp=Path(directory)
        api_port,web_port=free_port(),free_port()
        while web_port==api_port:
            web_port=free_port()
        (temp/'browser_settings.py').write_text('from config.settings import *\nDATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":'+repr(str(temp/'browser.sqlite3'))+'}}\n')
        env=os.environ.copy()
        env.update({'DJANGO_SETTINGS_MODULE':'browser_settings','PYTHONPATH':str(temp)+os.pathsep+str(ROOT/'backend'),
            'DJANGO_DEBUG':'true','DJANGO_SECURE_SSL_REDIRECT':'false','DJANGO_CACHE_BACKEND':'locmem',
            'DJANGO_ALLOWED_HOSTS':'127.0.0.1,localhost,testserver','CORS_ALLOWED_ORIGINS':f'http://127.0.0.1:{web_port}',
            'VITE_API_URL':f'http://127.0.0.1:{api_port}','E2E_PORT':str(web_port),'WORKTRACK_LIVE_E2E':'1',
            'E2E_USERNAME':'ui-smoke-admin','E2E_PASSWORD':'Test-'+secrets.token_urlsafe(24)+'-123'})
        def manage(*args):
            subprocess.run([sys.executable,'manage.py',*args],cwd=ROOT,env=env,check=True)
        manage('migrate','--noinput','--verbosity','0')
        manage('shell','-c',"import os; from django.contrib.auth import get_user_model; get_user_model().objects.create_superuser(username=os.environ['E2E_USERNAME'],password=os.environ['E2E_PASSWORD'],role='ADMIN')")
        with (temp/'backend.log').open('w') as log:
            backend=subprocess.Popen([sys.executable,'manage.py','runserver',f'127.0.0.1:{api_port}','--noreload'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+20
                while True:
                    try:
                        with urlopen(env['VITE_API_URL']+'/api/health/',timeout=1) as response:
                            if response.status==200: break
                    except (URLError,TimeoutError):
                        if backend.poll() is not None or time.monotonic()>deadline:
                            raise RuntimeError('Temporary backend did not become ready.')
                        time.sleep(.1)
                result=subprocess.run([npm,'run','test:e2e','--','e2e/live.spec.js'],cwd=ROOT,env=env)
                if result.returncode:
                    print('Temporary backend log:',(temp/'backend.log').read_text()[-3000:])
                return result.returncode
            finally:
                backend.terminate()
                try: backend.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    backend.kill();backend.wait()
                print('Disposable frontend/backend stopped; live database unchanged.')


if __name__=='__main__':
    raise SystemExit(main())
