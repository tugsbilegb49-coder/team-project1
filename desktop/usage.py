"""Durable local launcher uptime, excluding suspended/offline gaps.

Intervals are unioned when reporting, so overlapping launcher processes never
double-count a device's usage. No account credentials or activity content is stored.
"""

from datetime import datetime
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Ulaanbaatar')
CHECKPOINT_SECONDS = 5
MAX_GAP_SECONDS = 15


def month_start(year, month):
    return datetime(year, month, 1, tzinfo=ZONE).timestamp()


def next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def union_seconds(intervals, start, end):
    total, cursor = 0.0, start
    for left, right in sorted(intervals):
        left, right = max(left, start, cursor), min(right, end)
        if right > left:
            total += right - left
            cursor = right
    return total


class LauncherUsage:
    def __init__(self, path, *, clock=None, monotonic=None, autostart=True):
        self.path = Path(path)
        self.clock, self.monotonic = clock or time.time, monotonic or time.monotonic
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.session = str(uuid4())
        self.segment = None
        self.binding = None
        self.closed = False
        self.failed = False
        self.wall, self.mono = self.clock(), self.monotonic()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # SQLite and its rollback journal inherit the database's private mode.
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
            with self._connect() as db:
                db.execute(
                    'CREATE TABLE IF NOT EXISTS intervals (id INTEGER PRIMARY KEY, session TEXT NOT NULL, started REAL NOT NULL, ended REAL NOT NULL, CHECK (ended >= started))'
                )
                db.execute('CREATE INDEX IF NOT EXISTS usage_ended ON intervals(ended)')
                columns = {row[1] for row in db.execute('PRAGMA table_info(intervals)')}
                for name, kind in [('scope', 'TEXT'), ('device', 'TEXT'), ('event_id', 'TEXT'), ('synced_end', 'REAL')]:
                    if name not in columns:
                        db.execute(f'ALTER TABLE intervals ADD COLUMN {name} {kind}')
                self.segment = self._insert(db, self.wall)
                self.segment_start = self.wall
        except (OSError, sqlite3.Error):
            self.failed = True
        if autostart:
            self.thread = threading.Thread(target=self._run, name='launcher-monthly-usage', daemon=True)
            self.thread.start()

    def _connect(self):
        # Explicitly close connections: sqlite3's transaction context only commits.
        from contextlib import contextmanager

        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=2)
            try:
                with db:
                    yield db
            finally:
                db.close()

        return connection()

    def _run(self):
        while not self.stop.wait(CHECKPOINT_SECONDS):
            self.checkpoint()

    def _insert(self, db, now):
        scope, device = self.binding or (None, None)
        return db.execute(
            'INSERT INTO intervals(session, started, ended, scope, device, event_id) VALUES (?, ?, ?, ?, ?, ?)',
            (self.session, now, now, scope, device, str(uuid4())),
        ).lastrowid

    def bind(self, scope=None, device=None):
        """Only a verified account can own NEW intervals; never relabel history."""
        binding = (scope, str(device)) if scope and device else None
        with self.lock:
            if binding == self.binding or self.closed:
                return
            self.checkpoint()
            self.binding, self.segment = binding, None
            self.checkpoint()

    def pending(self, scope, device=None):
        with self.lock, self._connect() as db:
            return [
                dict(zip(('id', 'device_id', 'event_id', 'started_at', 'ended_at'), row))
                for row in db.execute(
                    'SELECT id, device, event_id, started, ended FROM intervals WHERE scope=? AND (? IS NULL OR device=?) AND ended>started '
                    'AND (synced_end IS NULL OR ended>synced_end) ORDER BY id LIMIT 100',
                    (scope, device, device),
                )
            ]

    def acknowledge(self, rows):
        with self.lock, self._connect() as db:
            for row in rows:
                db.execute(
                    'UPDATE intervals SET synced_end=MAX(COALESCE(synced_end,0),?) WHERE id=? AND event_id=?',
                    (row['ended_at'], row['id'], row['event_id']),
                )

    def checkpoint(self):
        with self.lock:
            if self.closed:
                return
            now, mono = self.clock(), self.monotonic()
            delta, elapsed = now - self.wall, mono - self.mono
            contiguous = 0 <= delta <= MAX_GAP_SECONDS and 0 <= elapsed <= MAX_GAP_SECONDS and abs(delta - elapsed) <= 2
            try:
                if not math.isfinite(now) or not math.isfinite(mono):
                    raise ValueError('Invalid clock')
                with self._connect() as db:
                    if contiguous and self.segment is not None:
                        changed = db.execute(
                            'UPDATE intervals SET ended=? WHERE id=? AND session=?', (now, self.segment, self.session)
                        ).rowcount
                        if changed != 1:
                            raise sqlite3.DatabaseError('Usage interval was removed')
                        if now - self.segment_start >= 3600:
                            self.segment = self._insert(db, now)
                            self.segment_start = now
                    else:
                        self.segment = self._insert(db, now)
                        self.segment_start = now
                self.failed = False
            except (OSError, sqlite3.Error, ValueError):
                self.failed = True
                # A later write must not invent time while the durable ledger was unavailable.
                self.segment = None
            self.wall, self.mono = now, mono

    def snapshot(self, scope=None):
        with self.lock:
            self.checkpoint()
            if self.failed:
                return {'available': False, 'error': 'Сарын хугацааг хадгалж чадсангүй. WorkTrack-аа дахин асаана уу.'}
            now = self.clock()
            try:
                with self._connect() as db:
                    intervals = (
                        list(
                            db.execute(
                                'SELECT started, ended FROM intervals WHERE scope=? ORDER BY started, ended', (scope,)
                            )
                        )
                        if scope
                        else []
                    )
                if any(not math.isfinite(start) or not math.isfinite(end) or end < start for start, end in intervals):
                    raise ValueError('Invalid usage history')
                first = min((row[0] for row in intervals), default=now)
                current = datetime.fromtimestamp(now, ZONE)
                earliest = datetime.fromtimestamp(min(first, now), ZONE)
                year, month = earliest.year, earliest.month
                months = []
                while (year, month) <= (current.year, current.month):
                    following = next_month(year, month)
                    end = month_start(*following)
                    months.append(
                        {
                            'month': f'{year:04d}-{month:02d}',
                            'seconds': union_seconds(intervals, month_start(year, month), min(end, now)),
                        }
                    )
                    year, month = following
                return {
                    'available': True,
                    'timezone': 'Asia/Ulaanbaatar',
                    'as_of': now,
                    'recorded_since': datetime.fromtimestamp(first, ZONE).isoformat() if intervals else None,
                    'current_month': f'{current.year:04d}-{current.month:02d}',
                    'month_ends_at': month_start(*next_month(current.year, current.month)),
                    'running': not self.closed and bool(self.binding and self.binding[0] == scope),
                    'months': list(reversed(months)),
                }
            except (OSError, sqlite3.Error, ValueError, OverflowError):
                return {
                    'available': False,
                    'error': 'Сарын хугацааны түүхийг уншиж чадсангүй. WorkTrack-аа дахин асаана уу.',
                }

    def close(self):
        self.stop.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
        with self.lock:
            if not self.closed:
                self.checkpoint()
                self.closed = True
