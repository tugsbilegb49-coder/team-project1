from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import ssl
import threading
from urllib.request import Request

import pytest

from agent.transport import PIN_ENV, PinMismatch, open_url
from desktop.gateway import check_server, normalize_server
from desktop.tls import TLSProxy, ensure_certificate, pairing_code


class Django(BaseHTTPRequestHandler):
    """Stands in for runserver on 127.0.0.1:8000 and echoes what reached it."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/api/health/':
            data = {'service': 'worktrack-api', 'protocol': 1}
        else:
            data = {key: self.headers.get(key) for key in ('X-Forwarded-For', 'X-Forwarded-Proto', 'Authorization')}
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def office(tmp_path):
    django = ThreadingHTTPServer(('127.0.0.1', 0), Django)
    threading.Thread(target=django.serve_forever, daemon=True).start()
    cert, key, digest = ensure_certificate(tmp_path / 'tls', ['192.168.1.20'])
    proxy = TLSProxy(('127.0.0.1', 0), cert, key, f'http://127.0.0.1:{django.server_port}')
    proxy.start()
    yield f'https://127.0.0.1:{proxy.server_port}', digest
    proxy.close()
    django.shutdown()
    django.server_close()


def test_the_certificate_and_its_code_stay_the_same_after_a_restart(tmp_path):
    first = ensure_certificate(tmp_path, ['192.168.1.20'])
    again = ensure_certificate(tmp_path, ['10.0.0.7'])  # A new IP address must not change the code.
    assert first == again
    assert pairing_code(first[2]) == '-'.join(first[2][i : i + 4].upper() for i in (0, 4, 8))


def test_pairing_with_the_code_pins_the_certificate(office, monkeypatch):
    url, digest = office
    monkeypatch.delenv(PIN_ENV, raising=False)
    with pytest.raises(ValueError, match='серверийн кодыг оруулна'):
        check_server(url)
    with pytest.raises(ValueError, match='код таарсангүй'):
        check_server(url, code='0000-0000-0000')
    assert check_server(url, code=pairing_code(digest).lower()) == digest


def test_requests_carry_the_computers_address_and_ignore_forged_forwarding(office):
    url, digest = office
    request = Request(url + '/api/me/', headers={'X-Forwarded-For': '6.6.6.6', 'Authorization': 'Bearer t'})
    with open_url(request, timeout=5, pin=digest) as response:
        data = json.load(response)
    assert data == {'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Proto': 'https', 'Authorization': 'Bearer t'}


def test_another_certificate_is_refused_once_paired(office, tmp_path):
    url, _ = office
    other = ensure_certificate(tmp_path / 'impostor')[2]
    with pytest.raises(OSError) as error:
        open_url(Request(url + '/api/health/'), timeout=5, pin=other)
    assert isinstance(error.value.reason, PinMismatch)


def test_plain_http_to_the_https_port_does_not_break_it(office):
    url, digest = office
    port = int(url.rsplit(':', 1)[1])
    with socket.create_connection(('127.0.0.1', port), timeout=5) as raw:
        raw.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        try:
            raw.recv(100)
        except OSError:
            pass
    with open_url(Request(url + '/api/health/'), timeout=5, pin=digest) as response:
        assert json.load(response)['service'] == 'worktrack-api'


def test_without_a_pin_an_unknown_certificate_is_rejected(office, monkeypatch):
    url, _ = office
    monkeypatch.delenv(PIN_ENV, raising=False)
    with pytest.raises(OSError) as error:
        open_url(Request(url + '/api/health/'), timeout=5)
    assert isinstance(getattr(error.value, 'reason', error.value), ssl.SSLCertVerificationError)


def test_the_office_https_port_is_understood_without_a_scheme():
    assert normalize_server('192.168.1.20:8443') == 'https://192.168.1.20:8443'
    assert normalize_server('192.168.1.20:8000') == 'http://192.168.1.20:8000'
