from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from desktop.usage import LauncherUsage, ZONE
from desktop.usage_sync import UsageSync, usage_scope
from agent.main import AgentError, ApiError


class Clock:
    def __init__(self, when='2026-11-01T00:00:00'):
        self.wall = datetime.fromisoformat(when).replace(tzinfo=ZONE).timestamp()
        self.mono = 0

    def advance(self, seconds, awake=None):
        self.wall += seconds
        self.mono += seconds if awake is None else awake

    def ledger(self, path):
        return LauncherUsage(path, clock=lambda:self.wall, monotonic=lambda:self.mono, autostart=False)


def total(ledger, scope='alice', month='2026-11'):
    return next(row['seconds'] for row in ledger.snapshot(scope)['months'] if row['month'] == month)


def test_restart_excludes_closed_time_and_isolates_accounts(tmp_path):
    path, clock = tmp_path/'usage.sqlite3', Clock()
    first = clock.ledger(path)
    clock.advance(5)  # Unlinked time never assigned to a future account.
    first.bind('alice', 'laptop')
    clock.advance(10)
    first.close()
    clock.advance(600)
    second = clock.ledger(path)
    second.bind('alice', 'laptop')
    clock.advance(10)
    assert total(second) == 20
    second.bind('bob', 'laptop2')
    clock.advance(5)
    assert total(second, 'alice') == 20
    assert total(second, 'bob') == 5
    assert not second.snapshot('alice')['running']
    assert not second.pending('nobody')
    second.close()


@pytest.mark.parametrize('awake', [0, 20])
def test_sleep_and_clock_jump_do_not_add_unobserved_time(tmp_path, awake):
    clock = Clock()
    ledger = clock.ledger(tmp_path/'usage.sqlite3')
    ledger.bind('alice', 'laptop')
    clock.advance(5); ledger.checkpoint()
    clock.advance(20, awake); ledger.checkpoint()
    clock.advance(5)
    assert total(ledger) == 10
    clock.advance(3600, 1); ledger.checkpoint()
    clock.advance(5)
    assert total(ledger) == 15  # A wall-clock jump must not invent an hour.
    ledger.close()


def test_month_boundary_union_and_idempotent_upload_ack(tmp_path):
    clock = Clock('2026-10-31T23:59:55')
    path = tmp_path/'usage.sqlite3'
    first, second = clock.ledger(path), clock.ledger(path)
    first.bind('alice', 'laptop'); second.bind('alice', 'laptop')
    clock.advance(10)
    first.checkpoint(); second.checkpoint()
    assert total(first, month='2026-10') == 5
    assert total(first) == 5  # Overlapping launches count once.
    rows = first.pending('alice', 'laptop')
    clock.advance(5); first.checkpoint()
    first.acknowledge(rows)  # An older in-flight upload must not ack new time.
    assert len(first.pending('alice', 'laptop')) == 1
    first.acknowledge(first.pending('alice', 'laptop'))
    assert not first.pending('alice', 'laptop')
    first.close(); second.close()


def test_corrupt_ledger_is_reported_and_not_erased(tmp_path):
    path = tmp_path/'usage.sqlite3'
    path.write_bytes(b'not a sqlite database')
    ledger = Clock().ledger(path)
    assert not ledger.snapshot('alice')['available']
    ledger.close()
    assert path.read_bytes() == b'not a sqlite database'


def test_hourly_rotation_bounds_uploaded_intervals(tmp_path):
    clock = Clock()
    ledger = clock.ledger(tmp_path/'usage.sqlite3')
    ledger.bind('alice', 'laptop')
    for _ in range(721):
        clock.advance(5); ledger.checkpoint()
    rows = ledger.pending('alice')
    assert len(rows) == 2
    assert sum(row['ended_at']-row['started_at'] for row in rows) == 3605
    assert max(row['ended_at']-row['started_at'] for row in rows) <= 3615
    ledger.close()


def test_sync_retains_offline_queue_retries_and_never_sends_to_other_account(tmp_path, monkeypatch):
    import threading
    clock = Clock()
    ledger = clock.ledger(tmp_path/'usage.sqlite3')
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'api_url':'http://local', 'device_id':'laptop'}))
    controller = SimpleNamespace(lock=threading.RLock(), closed=False, owner={'user_id':1}, api='http://local',
        tokens=tmp_path/'tokens', config=config, usage=ledger)
    client = Mock()
    client.get.return_value = {'id':1}
    monkeypatch.setattr('desktop.usage_sync.ApiClient', lambda *args:client)
    sync = UsageSync(controller, autostart=False)
    sync.cycle()
    scope = usage_scope(controller.api, 1)
    clock.advance(5); ledger.checkpoint()
    client.get.side_effect = AgentError('offline')
    sync.cycle()
    assert ledger.pending(scope)
    clock.advance(5); ledger.checkpoint()
    client.get.side_effect = None
    sync.cycle()
    assert not ledger.pending(scope)
    assert len(client._authenticated_post.call_args.args[1]['intervals']) == 1
    clock.advance(5); ledger.checkpoint()
    client.get.return_value = {'id':2}
    client._authenticated_post.reset_mock()
    sync.cycle()
    assert not client._authenticated_post.called
    assert ledger.pending(scope)
    assert ledger.binding is None
    client.get.return_value = {'id':1}
    client._authenticated_post.side_effect = ApiError(403, 'revoked')
    sync.cycle()
    assert ledger.binding is None
    ledger.close()
