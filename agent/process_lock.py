"""One collector of each kind per workspace, including manual CLI starts."""
from contextlib import contextmanager
import os
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    pass


@contextmanager
def collector_lock(kind):
    directory=Path(__file__).resolve().parents[1]/'.runtime'
    directory.mkdir(exist_ok=True)
    path=directory/(kind+'.lock')
    with path.open('a+b') as stream:
        os.chmod(path,0o600)
        if os.name=='nt':
            import msvcrt
            if path.stat().st_size==0: stream.write(b'0');stream.flush()
            stream.seek(0)
            try: msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc: raise AlreadyRunningError(f'{kind} collector аль хэдийн ажиллаж байна.') from exc
        else:
            import fcntl
            try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise AlreadyRunningError(f'{kind} collector аль хэдийн ажиллаж байна.') from exc
        try: yield
        finally:
            if os.name=='nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream,fcntl.LOCK_UN)
