"""What the last backup cycle did, for the admin page and notifications (backups/status.json).

The backup scheduler and the web server are separate processes (or containers sharing the
backups volume), so the result is kept in a small file next to the backups.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import time

from django.conf import settings
from django.utils import timezone

STALE_AFTER = timedelta(hours=36)  # The scheduler makes one backup a day.


def backup_dir():
    return settings.BASE_DIR / 'backups'


def status_path():
    return backup_dir() / 'status.json'


def read_status():
    try:
        value = json.loads(status_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_status(**values):
    path = status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**(read_status() or {}), **values, 'checked_at': timezone.now().isoformat()}
    fd, name = tempfile.mkstemp(prefix='.status-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        for attempt in range(40):  # Windows may briefly lock a file the web server is reading.
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if os.name != 'nt' or attempt == 39:
                    raise
                time.sleep(0.05)
    finally:
        Path(name).unlink(missing_ok=True)


def copy_dir_setting():
    """(directory, where it comes from): the server environment wins over the admin page."""
    configured = os.environ.get('BACKUP_COPY_DIR', '').strip()
    if configured:
        return configured, 'environment'
    from users.operations import current_settings

    value = current_settings().backup_copy_dir
    return (value, 'settings') if value else ('', None)


def problems(status=None):
    """Alert kinds for the admin: the last cycle failed, or no backup for too long."""
    status = read_status() if status is None else status
    if not status:
        return []
    found = []
    if status.get('error'):
        found.append('backup_failed')
    try:
        last = datetime.fromisoformat(status['last_success_at'])
    except (KeyError, TypeError, ValueError):
        last = None
    if last is None or timezone.now() - last > STALE_AFTER:
        found.append('backup_stale')
    return found
