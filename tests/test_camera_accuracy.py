import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from src import camera_accuracy
from src.camera_accuracy import STEPS, Session, evaluate, handler_for, score


def rows(step, expected, confidences):
    return [{'step': step, 'expected': expected, 'confidence': value, 'ms': 40} for value in confidences]


SAMPLES = (
    rows(0, 'present', [0.9, 0.85, 0.8, 0.88])
    + rows(1, 'absent', [0.0, 0.0, 0.12, 0.0])
    + rows(2, 'present', [0.42, 0.38, 0.5, 0.31])  # Head down over a phone: weaker.
    + rows(3, 'present', [0.6, 0.55, 0.7, 0.66])
    + rows(4, 'absent', [0.0, 0.2, 0.0, 0.0])
)


def test_scores_compare_the_detection_with_what_the_person_did():
    result = score(SAMPLES, 0.45)
    assert result['present_detected'] == pytest.approx(9 / 12)  # Three phone samples were missed.
    assert result['absent_detected'] == 1.0
    assert result['accuracy'] == pytest.approx(17 / 20)


def test_the_best_threshold_and_per_step_results_are_reported():
    result = evaluate(SAMPLES, current=0.45)
    # 0.25 and 0.30 both separate every sample; the one nearer the current setting wins.
    assert result['best']['threshold'] == 0.3 and result['best']['accuracy'] == 1.0
    assert [step['accuracy'] for step in result['steps']] == [1.0, 1.0, 0.25, 1.0, 1.0]
    assert result['steps'][2]['median_confidence'] == 0.4
    assert result['median_detection_ms'] == 40 and result['samples'] == 20
    with pytest.raises(ValueError):
        evaluate([])


def test_the_guidance_page_starts_only_from_itself(monkeypatch):
    session = Session(0.45)
    session.stage = 'ready'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(session))
    monkeypatch.setattr(camera_accuracy, 'PORT', server.server_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f'127.0.0.1:{server.server_port}'

    def call(method, path, headers):
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    try:
        status, body = call('GET', '/state', {'Host': host})
        assert status == 200 and json.loads(body)['stage'] == 'ready' and json.loads(body)['steps'] == len(STEPS)
        assert call('POST', '/start', {'Host': host, 'Origin': 'https://evil.example'})[0] == 403
        assert not session.started.is_set()
        assert call('POST', '/start', {'Host': host, 'Origin': 'http://' + host})[0] == 200
        assert session.started.is_set()
        assert call('GET', '/', {'Host': 'evil.example'})[0] == 403
    finally:
        server.shutdown()
        server.server_close()
