import csv
from datetime import datetime, timedelta, timezone
import os
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.detector import ObjectDetector
from src.presence import PresenceLogger, PresenceMonitor
from src.api_logger import PresenceEventUploader
from src.consent import ConsentGuard
from evaluate_camera import evaluate_presence


def test_person_threshold_filters_other_objects_and_disables_saving():
    model = Mock(names={0: 'person', 1: 'laptop'})
    def box(cls, confidence):
        return SimpleNamespace(cls=[cls], conf=[confidence], xyxy=np.array([[1, 2, 3, 4]]))
    model.predict.return_value = [SimpleNamespace(boxes=[box(0, .44), box(1, .99)])]
    detector = ObjectDetector(confidence_threshold=.45, model=model)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    assert detector.detect_presence(frame) == {'present': False, 'confidence': 0}
    model.predict.return_value = [SimpleNamespace(boxes=[box(0, .45), box(0, .81)])]
    assert detector.detect_presence(frame) == {'present': True, 'confidence': .81}
    assert model.predict.call_args.kwargs == {'conf': .45, 'verbose': False, 'save': False,
                                             'save_txt': False, 'save_crop': False, 'show': False}


@pytest.mark.parametrize('threshold', [0, -1, 1.1, float('nan'), True, '0.5'])
def test_bad_threshold_fails_before_loading_model(threshold):
    with pytest.raises(ValueError):
        ObjectDetector(confidence_threshold=threshold, model=Mock())


def test_presence_log_contains_only_metadata_and_is_private(tmp_path):
    path = tmp_path/'presence.csv'
    logger = PresenceLogger(path)
    try:
        logger.log(True, .87654321)
        logger.log(False, 0)
        with pytest.raises(ValueError): logger.log(True, float('nan'))
    finally:
        logger.close()
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert set(rows[0]) == {'timestamp', 'present', 'confidence'}
    assert [r['present'] for r in rows] == ['1', '0']
    assert path.stat().st_mode & 0o777 == 0o600


def test_corrupt_control_fails_closed(tmp_path):
    path = tmp_path/'control.json'
    monitor = PresenceMonitor({'control_file': str(path)})
    assert not monitor.paused()
    path.write_text('{broken')
    assert monitor.paused()
    path.write_text('{"paused":true}')
    assert monitor.paused()


def test_presence_uploader_uses_own_route_and_replays_queue(tmp_path):
    uploader = PresenceEventUploader('http://localhost', str(tmp_path/'tokens.json'),
        device_config_file=str(tmp_path/'device.json'), queue_file=tmp_path/'queue.json')
    with patch.object(uploader, '_post') as post, patch.object(uploader, '_read_tokens', return_value={'access': 'fake', 'refresh': 'fake'}):
        try:
            uploader.log(True, .8)
            assert uploader.flush(1)
            assert post.call_args.args[0] == '/api/camera-presence/ingest/'
            assert set(post.call_args.args[1]) == {'timestamp', 'present', 'confidence'}
        finally:
            uploader.close()


def test_binary_metrics_include_false_positives_false_negatives_and_missing_coverage():
    rows = [dict(expected=a, predicted=p, confidence=.8) for a, p in [(1,1), (1,0), (0,1), (0,0)]]
    result = evaluate_presence(rows)
    assert result['accuracy'] == result['precision'] == result['recall'] == result['f1'] == .5
    assert result['confusion_matrix'] == {'TP':1, 'FP':1, 'TN':1, 'FN':1}
    assert evaluate_presence([dict(expected=0, predicted=0, confidence=0)])['recall'] is None
    with pytest.raises(ValueError): evaluate_presence([])


def test_consent_lease_expires_and_network_failure_pauses_capture():
    clock = [0]
    check = Mock(return_value=True)
    guard = ConsentGuard(check, clock=lambda: clock[0])
    assert not guard.allowed()
    guard.refresh()
    assert guard.allowed()
    clock[0] = 3.01
    assert not guard.allowed()
    check.side_effect = OSError('offline')
    guard.refresh()
    assert not guard.allowed()
    check.side_effect = None
    check.return_value = False
    guard.refresh()
    assert not guard.allowed()


def test_late_consent_status_cannot_undo_upload_denial():
    entered, release = threading.Event(), threading.Event()
    def check():
        entered.set();release.wait(timeout=2)
        return True
    guard = ConsentGuard(check)
    thread = threading.Thread(target=guard.refresh)
    thread.start()
    try:
        assert entered.wait(timeout=1)
        guard.invalidate()
    finally:
        release.set();thread.join(timeout=2)
    assert not guard.allowed()


def run_fake_monitor(tmp_path, *, paused=False, allowed=True, revoke_during_inference=False):
    cv, detector, uploader, logger = Mock(), Mock(), Mock(), Mock()
    cv.VideoCapture.return_value.isOpened.return_value = True
    cv.VideoCapture.return_value.read.return_value = (True, np.zeros((10, 10, 3), dtype=np.uint8))
    active = [allowed]
    uploader.consent_guard.allowed.side_effect = lambda: active[0]
    def detect(*args):
        if revoke_during_inference: active[0] = False
        return {'present': True, 'confidence': .8}
    detector.detect_presence.side_effect = detect
    cv.waitKey.side_effect = [ord('q')] if paused else [0, 0, ord('q')]
    monitor = PresenceMonitor({'model_name': 'fake', 'confidence_threshold': .45, 'camera_index': 0,
                               'control_file': str(tmp_path/'control.json'), 'api_sync': {'enabled': True}})
    with patch.dict('sys.modules', {'cv2': cv}), patch('src.detector.ObjectDetector', return_value=detector), \
         patch('src.camera_capture.open_camera',side_effect=cv.VideoCapture), \
         patch('src.presence.PresenceLogger', return_value=logger), \
         patch('src.api_logger.PresenceEventUploader', return_value=uploader), \
         patch.object(monitor, 'paused', return_value=paused), patch('src.presence.time.sleep'):
        monitor.run()
    return cv, detector, logger, uploader


def test_quit_works_while_paused_without_opening_camera(tmp_path):
    cv, detector, logger, uploader = run_fake_monitor(tmp_path, paused=True)
    assert cv.waitKey.call_count == 1
    cv.VideoCapture.assert_not_called()
    logger.log.assert_not_called()
    uploader.close.assert_called_once()


def test_camera_never_opens_without_verified_server_consent(tmp_path):
    cv, detector, logger, _ = run_fake_monitor(tmp_path, allowed=False)
    cv.VideoCapture.assert_not_called()
    detector.detect_presence.assert_not_called()
    logger.log.assert_not_called()


def test_revoke_during_inference_discards_sample_and_releases_camera(tmp_path):
    cv, _, logger, uploader = run_fake_monitor(tmp_path, revoke_during_inference=True)
    cv.VideoCapture.return_value.read.assert_called_once()
    cv.VideoCapture.return_value.release.assert_called_once()
    logger.log.assert_not_called()
    uploader.log.assert_not_called()


def test_rotated_csv_files_stay_bounded_readable_and_private(tmp_path):
    path = tmp_path/'presence.csv'
    logger = PresenceLogger(path, max_bytes=256, backup_count=2)
    try:
        for _ in range(30): logger.log(True, .8)
    finally:
        logger.close()
    files = list(tmp_path.glob('presence.csv*'))
    assert len(files) == 3
    for file in files:
        assert file.stat().st_size <= 256
        assert file.stat().st_mode & 0o777 == 0o600
        with file.open() as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == ['timestamp', 'present', 'confidence']
            assert all(None not in row for row in reader)


def test_existing_oversized_csv_keeps_only_complete_latest_rows(tmp_path):
    path = tmp_path/'presence.csv'
    logger = PresenceLogger(path)
    for _ in range(20): logger.log(True, .8)
    logger.close()
    assert path.stat().st_size > 256
    logger = PresenceLogger(path, max_bytes=256)
    logger.close()
    assert path.stat().st_size <= 256
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows and all(set(row) == {'timestamp', 'present', 'confidence'} for row in rows)


def test_reducing_backup_limit_removes_only_generated_extra_backups(tmp_path):
    path = tmp_path/'presence.csv'
    logger = PresenceLogger(path, max_bytes=256, backup_count=3)
    for _ in range(30): logger.log(True, .8)
    logger.close()
    assert (tmp_path/'presence.csv.3').exists()
    manual = tmp_path/'presence.csv.20261106'
    manual.write_text('manual archive')
    logger = PresenceLogger(path, max_bytes=256, backup_count=1)
    logger.close()
    assert not (tmp_path/'presence.csv.2').exists()
    assert not (tmp_path/'presence.csv.3').exists()
    assert manual.read_text() == 'manual archive'


def test_csv_rolls_at_local_day_and_prunes_only_expired_owned_files(tmp_path):
    now = [datetime(2026, 11, 6, 12, tzinfo=timezone.utc)]
    path = tmp_path/'presence.csv'
    expired = tmp_path/'presence.csv.2'
    expired.write_text('old metadata')
    old = (now[0] - timedelta(days=8)).timestamp()
    os.utime(expired, (old, old))
    unrelated = tmp_path/'presence.csv.manual'
    unrelated.write_text('keep manual archive')
    logger = PresenceLogger(path, retention_days=7, clock=lambda: now[0])
    try:
        assert not expired.exists()
        logger.log(True, .8)
        now[0] += timedelta(days=1)
        logger.log(False, 0)
    finally:
        logger.close()
    assert (tmp_path/'presence.csv.1').exists()
    assert unrelated.read_text() == 'keep manual archive'
