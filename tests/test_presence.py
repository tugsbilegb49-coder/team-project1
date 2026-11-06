import csv
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.detector import ObjectDetector
from src.presence import PresenceLogger, PresenceMonitor
from src.api_logger import PresenceEventUploader
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
