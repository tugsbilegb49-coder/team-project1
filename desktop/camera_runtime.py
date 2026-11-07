"""Launch the bundled camera via LaunchServices, with an owned, stoppable session."""

import json
import plistlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def ensure_host(arguments):
    if sys.platform != 'darwin':
        return
    try:
        import _worktrack_camera_host  # noqa: F401  (availability check)
    except ImportError:
        os.execv(sys.executable, [sys.executable, '-u', '-m', 'desktop.camera_runtime', '--', *arguments])


def read_session(path, session):
    try:
        value = json.loads(Path(path).read_text())
        if value.get('session') == session and type(value.get('pid')) is int and value['pid'] > 1:
            return value
    except (OSError, ValueError, AttributeError):
        pass
    return None


def signal_owned_session(value, executable, signum):
    if not value:
        return
    try:
        command = subprocess.check_output(['/bin/ps', '-p', str(value['pid']), '-o', 'comm='], text=True).strip()
        if command == str(executable):
            os.kill(value['pid'], signum)
    except (OSError, subprocess.CalledProcessError):
        pass


def cancel_session(state, session, executable, opener, permit, timeout=3):
    # Deny late launches before waiting for a PID to appear.
    Path(permit).unlink(missing_ok=True)
    value = None
    signalled = set()
    deadline = time.monotonic() + timeout
    while opener.poll() is None and time.monotonic() < deadline:
        value = read_session(state, session) or value
        if value and value['pid'] not in signalled:
            signal_owned_session(value, executable, signal.SIGINT)
            signalled.add(value['pid'])
        time.sleep(0.05)
    value = read_session(state, session) or value
    if opener.poll() is None:
        signal_owned_session(value, executable, signal.SIGKILL)


def run_session(root, arguments, max_seconds=None):
    from desktop.build_camera_host import build

    root = Path(root).resolve()
    executable = build(root)
    info = plistlib.loads((executable.parents[1] / 'Info.plist').read_bytes())
    session = str(uuid.uuid4())
    directory = Path(info['WorkTrackSessionDirectory'])
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = directory / (session + '.json')
    log = directory / (session + '.log')
    permit = directory / (session + '.permit.json')
    log.touch(mode=0o600)
    from agent.token_store import atomic_json_write

    atomic_json_write(permit, {'session': session, 'wrapper_pid': os.getpid()})
    stopped = threading.Event()
    old = {signum: signal.signal(signum, lambda *_: stopped.set()) for signum in (signal.SIGINT, signal.SIGTERM)}
    command = [
        '/usr/bin/open',
        '-n',
        '-W',
        '-a',
        str(executable.parents[2]),
        '--stdout',
        str(log),
        '--stderr',
        str(log),
        '--env',
        'PYTHONUNBUFFERED=1',
        '--env',
        'YOLO_CONFIG_DIR=' + str(root / '.runtime/ultralytics'),
        '--args',
        '--session',
        session,
        *map(str, arguments),
    ]
    opener = None
    value = None
    started = time.monotonic()
    try:
        opener = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
        while True:
            value = read_session(state, session) or value
            if stopped.is_set() or (max_seconds is not None and time.monotonic() - started > max_seconds):
                if not stopped.is_set():
                    print('Camera host timeout; phase:', value.get('phase') if value else 'launching', file=sys.stderr)
                cancel_session(state, session, executable, opener, permit)
                return 130
            if opener.poll() is not None:
                value = read_session(state, session) or value
                if value and value.get('complete'):
                    return int(value['exit_code'])
                return 76
            if value is None and time.monotonic() - started > 30:
                print(
                    'Camera host ассангүй. macOS-ийн зөвшөөрлийн цонх болон camera session log-ийг шалгана уу.',
                    file=sys.stderr,
                )
                return 76
            time.sleep(0.1)
    finally:
        permit.unlink(missing_ok=True)
        value = read_session(state, session) or value
        if opener is not None and opener.poll() is None:
            cancel_session(state, session, executable, opener, permit, timeout=1)
            try:
                opener.wait(timeout=1)
            except subprocess.TimeoutExpired:
                opener.terminate()
                opener.wait(timeout=2)
        for signum, handler in old.items():
            signal.signal(signum, handler)
        if log.exists():
            with log.open(errors='replace') as stream:
                for line in stream:
                    print(line, end='', flush=True)
        state.unlink(missing_ok=True)
        log.unlink(missing_ok=True)


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ['--']:
        arguments = arguments[1:]
    try:
        return run_session(ROOT, [str(ROOT / 'main.py'), *arguments])
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('Camera launcher бэлтгэхэд алдаа гарлаа:', error, file=sys.stderr)
        return 70


if __name__ == '__main__':
    raise SystemExit(main())
