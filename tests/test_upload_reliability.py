import json
import os
import multiprocessing
import threading
import time
from unittest.mock import Mock, patch

import pytest
from agent.main import PendingUploader, ApiError
from agent.token_store import save_tokens, read_tokens, remove_tokens, StaleTokenError
from src.api_logger import CameraEventUploader, CameraAPISyncError


def token_writer(path, prefix):
    for number in range(20):
        save_tokens(path, {'access': f'{prefix}-{number}', 'refresh': 'shared-refresh'})
        assert read_tokens(path)['refresh'] == 'shared-refresh'


def test_rejected_head_is_quarantined_and_valid_rows_continue(tmp_path):
    client = Mock()
    client.ingest.side_effect = [ApiError(400, 'invalid event', route='/api/computer-activity/ingest/'), None]
    path = tmp_path / 'pending.json'
    worker = PendingUploader(client, path)
    worker.append({'id': 1})
    worker.append({'id': 2})
    try:
        assert worker.flush(2)
    finally:
        worker.stop()
    assert worker.pending == []
    assert [call.args[0]['id'] for call in client.ingest.call_args_list] == [1, 2]
    rejected = json.loads((tmp_path / 'pending.rejected.json').read_text())
    assert rejected[0]['status'] == 400 and rejected[0]['event'] == {'id': 1}
    assert os.name == 'nt' or (tmp_path / 'pending.rejected.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    'status,route',
    [(401, None), (403, None), (404, None), (408, None), (429, None), (500, None), (400, '/api/auth/refresh/')],
)
def test_transient_auth_or_wrong_endpoint_errors_keep_queue(tmp_path, status, route):
    client = Mock()
    client.ingest.side_effect = ApiError(status, 'retry or fix login', route=route)
    worker = PendingUploader(client, tmp_path / 'pending.json')
    worker.append({'id': 1})
    try:
        assert not worker.flush(1)
    finally:
        worker.stop()
    assert worker.pending == [{'id': 1}]
    assert not (tmp_path / 'pending.rejected.json').exists()


def test_quarantine_disk_failure_does_not_drop_the_rejected_record(tmp_path):
    client = Mock()
    client.ingest.side_effect = ApiError(400, 'invalid')
    worker = PendingUploader(client, tmp_path / 'pending.json')
    worker.append({'id': 1})
    with patch('agent.main.quarantine_event', side_effect=OSError('disk unavailable')):
        try:
            assert not worker.flush(1)
        finally:
            worker.stop()
    assert worker.pending == [{'id': 1}]


def test_corrupt_quarantine_retains_event_and_worker_can_retry(tmp_path):
    client = Mock()
    client.ingest.side_effect = ApiError(400, 'invalid')
    rejected = tmp_path / 'pending.rejected.json'
    rejected.write_text('broken json')
    worker = PendingUploader(client, tmp_path / 'pending.json')
    worker.append({'id': 1})
    try:
        assert not worker.flush(1)
        assert worker.thread.is_alive()
        assert worker.pending == [{'id': 1}]
        assert rejected.read_text() == 'broken json'
        rejected.write_text('[]')
        assert worker.flush(1)
    finally:
        worker.stop()


def test_camera_log_never_waits_for_slow_http(tmp_path):
    save_tokens(tmp_path / 'tokens.json', {'access': 'fake', 'refresh': 'fake'})
    entered, release = threading.Event(), threading.Event()

    def slow_send(payload):
        entered.set()
        release.wait(timeout=3)

    camera = CameraEventUploader(
        'http://localhost', str(tmp_path / 'tokens.json'), queue_file=str(tmp_path / 'camera.json')
    )
    with patch.object(camera, '_send', side_effect=slow_send):
        try:
            start = time.monotonic()
            camera.log('WORKING', 1)
            assert time.monotonic() - start < 0.5
            assert entered.wait(timeout=1)
            start = time.monotonic()
            camera.log('IDLE', 1)
            assert time.monotonic() - start < 0.5
            release.set()
            assert camera.flush(2)
        finally:
            release.set()
            camera.close()


def test_camera_quarantines_bad_event_and_uploads_next(tmp_path):
    save_tokens(tmp_path / 'tokens.json', {'access': 'fake', 'refresh': 'fake'})
    camera = CameraEventUploader(
        'http://localhost', str(tmp_path / 'tokens.json'), queue_file=str(tmp_path / 'camera.json')
    )
    invalid = CameraAPISyncError('invalid camera event')
    invalid.status = 400
    invalid.route = '/api/activity-events/ingest/'
    with patch.object(camera, '_send', side_effect=[invalid, None]) as send:
        try:
            camera.log('WORKING', 1)
            camera.log('IDLE', 1)
            assert camera.flush(2)
            assert send.call_count == 2
        finally:
            camera.close()
    assert len(json.loads(camera._worker.path.with_name(camera._worker.path.stem + '.rejected.json').read_text())) == 1


def test_concurrent_processes_write_complete_private_token_files(tmp_path):
    path = tmp_path / 'tokens.json'
    save_tokens(path, {'access': 'initial', 'refresh': 'shared-refresh'})
    context = multiprocessing.get_context('spawn')
    processes = [context.Process(target=token_writer, args=(str(path), prefix)) for prefix in ('agent', 'camera')]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
    assert read_tokens(path)['refresh'] == 'shared-refresh'
    assert os.name == 'nt' or path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('*.tmp'))


def test_old_refresh_cannot_resurrect_logout_or_overwrite_new_login(tmp_path):
    path = tmp_path / 'tokens.json'
    save_tokens(path, {'access': 'old', 'refresh': 'old-refresh'})
    remove_tokens(path, 'old-refresh')
    with pytest.raises(StaleTokenError):
        save_tokens(path, {'access': 'late', 'refresh': 'old-refresh'}, expected_refresh='old-refresh')
    assert not path.exists()
    save_tokens(path, {'access': 'new', 'refresh': 'new-refresh'})
    with pytest.raises(StaleTokenError):
        save_tokens(path, {'access': 'late', 'refresh': 'old-refresh'}, expected_refresh='old-refresh')
    with pytest.raises(StaleTokenError):
        remove_tokens(path, 'old-refresh')
    assert read_tokens(path) == {'access': 'new', 'refresh': 'new-refresh'}


def test_windows_replace_retries_while_a_reader_holds_the_file(tmp_path):
    from agent import token_store

    path = tmp_path / 'config.json'
    real_replace = os.replace
    attempts = []

    def flaky_replace(source, destination):
        attempts.append(destination)
        if len(attempts) < 3:
            raise PermissionError('[WinError 5] Access is denied')
        real_replace(source, destination)

    with (
        patch.object(token_store, 'WINDOWS', True),
        patch.object(token_store.os, 'replace', side_effect=flaky_replace),
        patch.object(token_store.time, 'sleep'),
    ):
        token_store.atomic_json_write(path, {'device_name': 'Миний компьютер'})
    assert len(attempts) == 3
    assert json.loads(path.read_text(encoding='utf-8')) == {'device_name': 'Миний компьютер'}
