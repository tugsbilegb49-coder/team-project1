"""Private atomic token writes with cross-process compare-and-swap protection."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time

WINDOWS = os.name == 'nt'


class StaleTokenError(RuntimeError):
    pass


def atomic_write_bytes(path, data):
    """Write a private file (mode 600) so readers see either the old or the new content."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.chmod(name, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_json_write(path, value):
    atomic_write_bytes(path, json.dumps(value, ensure_ascii=False).encode('utf-8'))


def _replace(source, destination, attempts=40):
    """os.replace that tolerates Windows briefly locking a file another process is reading."""
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if not WINDOWS or attempt == attempts - 1:
                raise
            time.sleep(0.05)


def read_tokens(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or any(
        not isinstance(value.get(key), str) or not value[key] for key in ('access', 'refresh')
    ):
        raise ValueError('Saved login does not contain valid token strings.')
    return value


@contextmanager
def token_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + '.lock')
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+b') as stream:
        if os.name == 'nt':
            import msvcrt

            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b'0')
                stream.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def save_tokens(path, tokens, expected_refresh=None):
    with token_lock(path):
        if expected_refresh is not None:
            try:
                current = read_tokens(path)
            except (OSError, ValueError):
                raise StaleTokenError('Login changed or was removed; refresh result discarded.')
            if current['refresh'] != expected_refresh:
                raise StaleTokenError('A newer login replaced this session; refresh result discarded.')
        atomic_json_write(path, tokens)


def remove_tokens(path, expected_refresh):
    with token_lock(path):
        try:
            current = read_tokens(path)
        except FileNotFoundError:
            return
        if current['refresh'] != expected_refresh:
            raise StaleTokenError('A newer login exists; it was not removed.')
        Path(path).unlink(missing_ok=True)
