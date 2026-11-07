"""Local web gateway for a team computer: serves the built web app and forwards its API calls.

The browser only ever talks to http://127.0.0.1:5173. This gateway answers with the files in
dist/ (no Node.js needed), forwards /api/... to the organisation's server and /desktop/... to the
local control on 8766. Because the forwarding happens here, the server needs no CORS settings and
the page never mixes https and http. Until a server address is saved it shows a small page that
asks for it.
"""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import ssl
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request

from agent.transport import open_url

MAX_BODY = 25 * 1024 * 1024
HOP_BY_HOP = {
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
    'host',
    'content-length',
    # Forwarding headers are set by whoever forwards; a client never chooses them.
    'x-forwarded-for',
    'x-forwarded-proto',
    'x-forwarded-host',
    'forwarded',
}


def normalize_server(value):
    """'192.168.1.20:8000' or 'https://worktrack.example.mn/' -> scheme://host[:port]."""
    value = (value or '').strip()
    if value and '://' not in value:
        # 8443 is the office server's HTTPS port (worktrack.py --share).
        value = ('https://' if value.rstrip('/').endswith(':8443') else 'http://') + value
    parts = urlsplit(value)
    try:
        parts.port  # Raises ValueError for a port that is not a number in range.
    except ValueError:
        parts = None
    if (
        not parts
        or parts.scheme not in ('http', 'https')
        or not re.fullmatch(r'[A-Za-z0-9.-]+', parts.hostname or '')
        or parts.path not in ('', '/')
        or parts.query
        or parts.username
    ):
        raise ValueError(
            'Серверийн хаягийг жишээ нь https://worktrack.company.mn эсвэл 192.168.1.20:8000 гэж оруулна уу.'
        )
    return f'{parts.scheme}://{parts.netloc}'


class ServerProblem(ValueError):
    """A message for the person entering the address."""


SELF_SIGNED = {18, 19, 20, 21}  # OpenSSL: a certificate no authority vouches for, like an office server's.


def needs_code(error):
    reason = getattr(error, 'reason', error)
    if not isinstance(reason, ssl.SSLCertVerificationError):
        return False
    if reason.verify_code not in SELF_SIGNED:
        # Expired, or made for another name: a real problem on the server, not a missing code.
        raise ServerProblem(
            f'Серверийн HTTPS гэрчилгээ хүчингүй байна ({reason.verify_message}). Админд хэлнэ үү.'
        ) from error
    return True


def check_server(url, timeout=8, code=None):
    """The certificate pin to keep for `url` (None when no pin is needed).

    Raises ValueError (in Mongolian) unless `url` is a WorkTrack API server. An office server's own
    certificate is accepted only when `code` matches the start of its fingerprint.
    """
    from desktop.tls import fingerprint, normalize_code

    pin = None
    try:
        try:
            response = open_url(Request(url + '/api/health/'), timeout=timeout)
        except URLError as exc:
            if not needs_code(exc):
                raise
            code = normalize_code(code)
            if len(code) < 12:
                raise ServerProblem(
                    'Энэ бол оффисын сервер. Серверийн «Сервер ба backup» хуудас эсвэл цонхонд гарсан '
                    'серверийн кодыг оруулна уу.'
                ) from exc
            parts = urlsplit(url)
            pem = ssl.get_server_certificate((parts.hostname, parts.port or 443), timeout=timeout)
            pin = fingerprint(ssl.PEM_cert_to_DER_cert(pem))
            if not pin.upper().startswith(code):
                raise ServerProblem(
                    'Серверийн код таарсангүй. Кодоо шалгана уу; таарахгүй хэвээр бол энэ сүлжээнд өөр '
                    'компьютер сервер мэт дүр эсгэж байж магадгүй тул админдаа хэлнэ үү.'
                ) from exc
            response = open_url(Request(url + '/api/health/'), timeout=timeout, pin=pin)
        with response:
            data = json.load(response)
    except ServerProblem:
        raise
    except HTTPError as exc:
        exc.close()
        raise ValueError(f'Сервер хариу өгсөн боловч WorkTrack биш байна (HTTP {exc.code}).') from exc
    except (URLError, OSError, http.client.HTTPException) as exc:
        raise ValueError('Сервертэй холбогдож чадсангүй. Хаяг, сүлжээгээ шалгана уу.') from exc
    except ValueError as exc:  # Not JSON.
        raise ValueError('Энэ хаяг дээр WorkTrack сервер ажиллахгүй байна.') from exc
    if not isinstance(data, dict) or data.get('service') != 'worktrack-api' or data.get('protocol') != 1:
        raise ValueError('Энэ хаяг дээр WorkTrack сервер ажиллахгүй байна.')
    return pin


SETUP_PAGE = """<!doctype html>
<html lang="mn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>WorkTrack — Сервертэй холбох</title>
<style>
body{font-family:system-ui,sans-serif;background:#f4f7f6;color:#1f2d2a;margin:0;padding:16px}
main{max-width:520px;margin:48px auto;background:#fff;border-radius:16px;padding:24px;box-shadow:0 2px 12px #0001}
label{display:block;font-weight:600;margin:16px 0 6px}
input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #bbcfc5;border-radius:8px;font:inherit}
button{margin-top:16px;background:#20b99a;color:#fff;border:0;border-radius:8px;padding:12px 18px;font:inherit;cursor:pointer}
button:disabled{opacity:.6}.muted{color:#5d6b67}[role=alert]{color:#b42318}
</style></head><body><main>
<h1>WorkTrack — Сервертэй холбох</h1>
<p>Байгууллагынхаа WorkTrack серверийн хаягийг оруулна уу. Хаягийг админаас асууна.</p>
<form id="f"><label for="u">Серверийн хаяг</label>
<input id="u" name="url" required placeholder="https://worktrack.company.mn эсвэл https://192.168.1.20:8443" autofocus>
<label for="c">Серверийн код <span class="muted">(зөвхөн оффисын сервер бол)</span></label>
<input id="c" name="code" autocomplete="off" spellcheck="false" placeholder="AB12-CD34-EF56">
<p id="e" role="alert"></p><button id="b">Холбох</button></form>
<p class="muted">Оффисын компьютер сервер бол түүний цонх эсвэл админы «Тохиргоо → Сервер ба backup» хуудсанд
гарсан хаяг, кодыг оруулна.</p>
</main><script>
document.getElementById('f').onsubmit = async (event) => {
  event.preventDefault();
  const button = document.getElementById('b'), error = document.getElementById('e');
  button.disabled = true; button.textContent = 'Шалгаж байна…'; error.textContent = '';
  try {
    const response = await fetch('/setup/server', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: document.getElementById('u').value, code: document.getElementById('c').value})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail);
    location.replace('/');
  } catch (failure) {
    error.textContent = failure.message || 'Холбож чадсангүй.';
    button.disabled = false; button.textContent = 'Холбох';
  }
};
</script></body></html>
"""


class Gateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, static_dir, api, desktop, on_server=None):
        """`on_server(url, pin)` saves a newly entered server address; offered only while api is None."""
        self.static_dir = Path(static_dir).resolve()
        self.api, self.desktop, self.on_server = api, desktop, on_server
        self.lock = threading.Lock()
        super().__init__(address, self.handler())

    def handler(self):
        return GatewayHandler

    def start(self):
        self.thread = threading.Thread(target=self.serve_forever, name='web-gateway', daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=3)


class GatewayHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(90)

    def log_message(self, *args):
        pass  # Never log URLs or tokens.

    def _send(self, status, body, content_type, headers=()):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        for name, value in headers:
            self.send_header(name, value)
        try:
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    def _handle(self):
        # Read the body before any reply: closing a socket with unread data resets the connection
        # and the browser would lose the response.
        self.data = self._body()
        if self.data is False:
            return self._json(413, {'detail': 'Хүсэлт хэт том байна.'})
        port = self.server.server_port
        # Refuse other host names so a web page cannot reach this server through DNS rebinding.
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self._json(403, {'detail': 'Local host шаардлагатай.'})
        path = self.path.split('?', 1)[0]
        if path == '/setup/server' and self.command == 'POST':
            return self._save_server()
        if path.startswith('/desktop/'):
            return self._forward(self.server.desktop)
        if path.startswith('/api/'):
            if not self.server.api:
                return self._json(503, {'detail': 'Эхлээд байгууллагын серверийн хаягийг оруулна уу.'})
            return self._forward(self.server.api)
        if self.command not in ('GET', 'HEAD'):
            return self._json(405, {'detail': 'Method not allowed.'})
        if not self.server.api:
            return self._send(200, SETUP_PAGE.encode(), 'text/html; charset=utf-8', [('Cache-Control', 'no-store')])
        return self._static(path)

    def _body(self):
        """The request body, None when there is none, False when it is too large or malformed."""
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            return False
        if length < 0 or length > MAX_BODY or self.headers.get('Transfer-Encoding'):
            self.close_connection = True
            return False
        return self.rfile.read(length) if length else None

    def _save_server(self):
        origin = self.headers.get('Origin')
        if origin and origin not in (
            f'http://127.0.0.1:{self.server.server_port}',
            f'http://localhost:{self.server.server_port}',
        ):
            return self._json(403, {'detail': 'Энэ хуудас тохиргоо өөрчлөх эрхгүй.'})
        if self.server.api or not self.server.on_server:
            return self._json(409, {'detail': 'Сервер аль хэдийн тохируулагдсан.'})
        try:
            data = json.loads(self.data or b'{}')
            url = normalize_server(data.get('url'))
            pin = check_server(url, code=data.get('code') or '')
            with self.server.lock:
                self.server.on_server(url, pin)
                self.server.api = url
        except (ValueError, AttributeError, OSError) as exc:
            return self._json(400, {'detail': str(exc) or 'Буруу хаяг.'})
        return self._json(200, {'server': url})

    def _forward(self, base, extra=None):
        headers = {name: value for name, value in self.headers.items() if name.lower() not in HOP_BY_HOP}
        headers.update(extra or {})
        request = Request(base + self.path, data=self.data, headers=headers, method=self.command)
        try:
            # Pinned to the office server's certificate when the launcher set WORKTRACK_SERVER_PIN.
            response = open_url(request, timeout=60)
        except HTTPError as exc:
            response = exc  # 4xx/5xx still carry the server's body for the page.
        except (URLError, OSError, http.client.HTTPException):
            return self._json(502, {'detail': 'Байгууллагын сервертэй холбогдож чадсангүй. Сүлжээгээ шалгана уу.'})
        with response:
            data = response.read()
            kept = [(name, value) for name, value in response.headers.items() if name.lower() not in HOP_BY_HOP]
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            kept = [(name, value) for name, value in kept if name.lower() != 'content-type']
            self._send(response.status if hasattr(response, 'status') else response.code, data, content_type, kept)

    def _static(self, path):
        root = self.server.static_dir
        target = (root / path.lstrip('/')).resolve()
        if root not in target.parents and target != root:
            return self._json(404, {'detail': 'Олдсонгүй.'})
        if not target.is_file():
            target = root / 'index.html'  # Client-side routes all load the app.
        if not target.is_file():
            return self._json(500, {'detail': 'Вэб хуудасны файлууд олдсонгүй (dist/).'})
        content_type = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type in ('application/javascript', 'image/svg+xml'):
            content_type += '; charset=utf-8'
        # Vite puts a content hash in asset names, so those can be cached for good.
        cache = 'public, max-age=31536000, immutable' if '/assets/' in path else 'no-cache'
        self._send(200, target.read_bytes(), content_type, [('Cache-Control', cache)])

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_PATCH(self):
        self._handle()

    def do_DELETE(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()
