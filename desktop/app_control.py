#!/usr/bin/env python3
"""Start/stop only the launcher instance created by the macOS applet."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop'])
    parser.add_argument('instance')
    args = parser.parse_args()
    import uuid

    instance = str(uuid.UUID(args.instance))
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    state = runtime / 'macos-app.json'
    if args.action == 'start':
        import fcntl

        with (runtime / 'launcher.lock').open('a+') as lock:
            for attempt in range(100):
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    try:
                        request = Request('http://127.0.0.1:8766/desktop/status/', headers={'X-WorkTrack-Desktop': '1'})
                        with urlopen(request, timeout=0.3):
                            pass
                    except HTTPError as error:
                        code = error.code
                        error.close()
                        if code == 401:
                            print('existing')
                            return
                    except (URLError, OSError):
                        pass
                    time.sleep(0.1)
            else:
                print('existing')
                return
        python = ROOT / '.venv/bin/python'
        with (runtime / 'app.log').open('a') as stream:
            process = subprocess.Popen(
                [
                    str(python) if python.exists() else sys.executable,
                    str(ROOT / 'worktrack.py'),
                    '--desktop',
                    '--app-id',
                    instance,
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        state.write_text(json.dumps({'pid': process.pid, 'instance': instance}))
        state.chmod(0o600)
        print('started')
    else:
        try:
            value = json.loads(state.read_text())
            if value['instance'] != instance:
                return
            pid = int(value['pid'])
            command = subprocess.check_output(['/bin/ps', '-p', str(pid), '-o', 'command='], text=True)
            cwd = subprocess.check_output(['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], text=True)
            if (
                str(ROOT / 'worktrack.py') in command
                and '--app-id ' + instance in command
                and '\nn' + str(ROOT) + '\n' in cwd
            ):
                os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
            pass


if __name__ == '__main__':
    main()
