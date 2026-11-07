from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import threading

import pytest

from desktop.gateway import Gateway, check_server, normalize_server


class FakeApi(BaseHTTPRequestHandler):
    """Stands in for the organisation's server and the local desktop control."""

    def log_message(self, *args):
        pass

    def _reply(self, status, data, headers=()):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/health/':
            return self._reply(200, {'service': 'worktrack-api', 'protocol': 1})
        if self.path.startswith('/api/me/'):
            return self._reply(401, {'detail': 'login'}, [('WWW-Authenticate', 'Bearer')])
        self._reply(200, {'path': self.path, 'host': self.headers['Host'], 'auth': self.headers.get('Authorization')})

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self._reply(201, {'echo': json.loads(body), 'origin': self.headers.get('Origin')})


@pytest.fixture
def api():
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeApi)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()


@pytest.fixture
def site(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<div id="root"></div>', encoding='utf-8')
    (tmp_path / 'assets' / 'app-1234.js').write_text('console.log(1)', encoding='utf-8')
    (tmp_path.parent / 'secret.txt').write_text('outside', encoding='utf-8')
    return tmp_path


def open_gateway(site, api, desktop=None, on_server=None):
    gateway = Gateway(('127.0.0.1', 0), site, api, desktop or api, on_server)
    gateway.start()
    return gateway


def call(gateway, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', gateway.server_port, timeout=10)
    headers = {'Host': f'127.0.0.1:{gateway.server_port}', **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    if data:
        headers['Content-Type'] = 'application/json'
    connection.request(method, path, body=data, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_serves_the_built_app_and_falls_back_to_index_for_app_routes(site, api):
    gateway = open_gateway(site, api)
    try:
        status, headers, body = call(gateway, 'GET', '/')
        assert status == 200 and b'id="root"' in body and headers['Cache-Control'] == 'no-cache'
        status, headers, body = call(gateway, 'GET', '/assets/app-1234.js')
        assert body == b'console.log(1)' and 'immutable' in headers['Cache-Control']
        assert call(gateway, 'GET', '/tasks/42')[2] == b'<div id="root"></div>'
        status, _, body = call(gateway, 'GET', '/../secret.txt')
        assert b'outside' not in body
    finally:
        gateway.close()


def test_forwards_api_calls_with_status_headers_and_body(site, api):
    gateway = open_gateway(site, api)
    try:
        status, _, body = call(gateway, 'GET', '/api/tasks/?page=2', headers={'Authorization': 'Bearer abc'})
        data = json.loads(body)
        assert status == 200 and data['path'] == '/api/tasks/?page=2' and data['auth'] == 'Bearer abc'
        assert data['host'] == api.removeprefix('http://')  # The real server's host, not the gateway's.
        status, headers, _ = call(gateway, 'GET', '/api/me/today/')
        assert status == 401 and headers['WWW-Authenticate'] == 'Bearer'
        status, _, body = call(gateway, 'POST', '/desktop/start/', {'a': 1}, {'Origin': 'http://127.0.0.1:5173'})
        assert status == 201 and json.loads(body) == {'echo': {'a': 1}, 'origin': 'http://127.0.0.1:5173'}
    finally:
        gateway.close()


def test_unreachable_server_gives_a_clear_502(site):
    gateway = open_gateway(site, 'http://127.0.0.1:9')
    try:
        status, _, body = call(gateway, 'GET', '/api/health/')
        assert status == 502 and 'сервертэй холбогдож чадсангүй' in json.loads(body)['detail']
    finally:
        gateway.close()


def test_other_host_names_are_refused(site, api):
    gateway = open_gateway(site, api)
    try:
        assert call(gateway, 'GET', '/', headers={'Host': 'evil.example:5173'})[0] == 403
        assert call(gateway, 'GET', '/api/health/', headers={'Host': 'evil.example:5173'})[0] == 403
    finally:
        gateway.close()


def test_first_run_page_saves_a_checked_server_address(site, api):
    saved = []
    gateway = open_gateway(site, None, desktop=api, on_server=saved.append)
    try:
        status, _, body = call(gateway, 'GET', '/')
        assert status == 200 and 'Сервертэй холбох'.encode() in body
        assert call(gateway, 'GET', '/api/health/')[0] == 503
        origin = {'Origin': f'http://127.0.0.1:{gateway.server_port}'}
        assert call(gateway, 'POST', '/setup/server', {'url': api}, {'Origin': 'https://evil.example'})[0] == 403
        status, _, body = call(gateway, 'POST', '/setup/server', {'url': 'not a url'}, origin)
        assert status == 400
        status, _, body = call(gateway, 'POST', '/setup/server', {'url': api.removeprefix('http://')}, origin)
        assert status == 200 and saved == [api]
        assert json.loads(call(gateway, 'GET', '/api/health/')[2])['service'] == 'worktrack-api'
        assert call(gateway, 'POST', '/setup/server', {'url': api}, origin)[0] == 409  # Only once.
    finally:
        gateway.close()


@pytest.mark.parametrize(
    'value,expected',
    [
        ('192.168.1.20:8000', 'http://192.168.1.20:8000'),
        (' https://worktrack.example.mn/ ', 'https://worktrack.example.mn'),
        ('http://office-pc.local:8000', 'http://office-pc.local:8000'),
    ],
)
def test_server_addresses_are_normalized(value, expected):
    assert normalize_server(value) == expected


@pytest.mark.parametrize(
    'value', ['', 'ftp://x', 'https://x.mn/some/path', 'http://', 'not a url', 'x.mn:99999', 'http://u:p@x.mn']
)
def test_bad_server_addresses_are_explained(value):
    with pytest.raises(ValueError):
        normalize_server(value)


def test_a_non_worktrack_server_is_rejected(site):
    other = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)  # Answers 501 to everything.
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        with pytest.raises(ValueError, match='WorkTrack'):
            check_server(f'http://127.0.0.1:{other.server_port}')
    finally:
        other.shutdown()
        other.server_close()
