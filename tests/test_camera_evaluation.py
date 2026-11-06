import pytest
from evaluate_camera import evaluate


def test_camera_metrics_require_labels_and_report_confusion():
    result=evaluate([{'expected':'WORKING','predicted':'WORKING'},{'expected':'PHONE','predicted':'WORKING'}])
    assert result['accuracy']==.5
    assert result['per_state']['WORKING']['precision']==.5
    assert result['per_state']['PHONE']['recall']==0
    assert result['per_state']['IDLE']['recall'] is None
    with pytest.raises(ValueError):
        evaluate([])
