import json
from pathlib import Path
from types import SimpleNamespace

from agent.version import is_newer, parse
from desktop.updates import UpdateCheck, message


def checker(tmp_path, answer):
    sent = []
    controller = SimpleNamespace(runtime=Path(tmp_path), api='http://server')
    fetch = answer if callable(answer) else lambda: answer
    return UpdateCheck(controller, autostart=False, fetch=fetch, send=sent.append), sent


def test_versions_compare_as_numbers():
    assert is_newer('1.10.0', '1.9.3') and is_newer('1.0.1', '1.0') and not is_newer('1.0', '1.0.0')
    assert not is_newer('', '1.0.0') and not is_newer('1.0.0-beta', '1.0.0') and parse('2.x') is None


def test_a_newer_version_is_offered_and_notified_once(tmp_path):
    item, sent = checker(tmp_path, {'client': {'version': '9.0.0', 'download_url': 'https://example.mn/a.zip'}})
    assert item.check() == {'version': '9.0.0', 'download_url': 'https://example.mn/a.zip'}
    item.check()
    assert sent == [message('9.0.0')]
    again, sent = checker(tmp_path, item.fetch)  # After a restart.
    again.check()
    assert sent == [] and json.loads((tmp_path / 'update-notice.json').read_text()) == {'version': '9.0.0'}


def test_same_or_older_versions_and_unsafe_links_offer_nothing(tmp_path):
    for client in (
        {'version': '1.0.0', 'download_url': 'https://example.mn/a.zip'},
        {'version': '0.9', 'download_url': 'https://example.mn/a.zip'},
        {'version': '9.0.0', 'download_url': 'javascript:alert(1)'},
        None,
    ):
        item, sent = checker(tmp_path, {'client': client})
        assert item.check() is None and sent == [], client


def test_offline_keeps_the_last_known_offer(tmp_path):
    answers = iter([{'client': {'version': '9.0.0', 'download_url': 'https://x.mn/a.zip'}}, OSError('offline')])

    def fetch():
        value = next(answers)
        if isinstance(value, Exception):
            raise value
        return value

    item, _ = checker(tmp_path, fetch)
    item.check()
    assert item.check() == {'version': '9.0.0', 'download_url': 'https://x.mn/a.zip'}
