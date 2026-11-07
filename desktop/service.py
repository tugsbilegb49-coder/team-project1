"""Loopback-only, authenticated controls for processes owned by this launcher."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from agent.main import ApiClient, AgentError, is_paused, set_paused
from agent.token_store import atomic_json_write, save_tokens


class DesktopError(RuntimeError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DesktopController:
    def __init__(self, root, api, python, shutdown, spawn=None, stop=None, started_at=None, usage=None, sync=True):
        self.root, self.api, self.python = Path(root), api, str(python)
        self.started_at = time.time() if started_at is None else started_at
        self.runtime = self.root / '.runtime'
        self.runtime.mkdir(exist_ok=True)
        from desktop.usage import LauncherUsage

        self.owns_usage = usage is None
        self.usage = usage if usage is not None else LauncherUsage(self.runtime / 'launcher-usage.sqlite3')
        self.tokens = self.root / 'agent/.agent_tokens.json'
        self.config = self.root / 'agent/config.json'
        self.control = self.root / 'agent/control.json'
        self.metadata = self.runtime / 'desktop-session.json'
        self.lock = threading.RLock()
        self.processes, self.logs = {}, []
        self.spawn = spawn or self._spawn
        if stop is None:
            from worktrack import stop_process

            stop = stop_process
        self.stop = stop
        self.shutdown = shutdown
        self.preparing, self.setup_error = False, False
        self.install_process = None
        self.closed = False
        try:
            self.owner = json.loads(self.metadata.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.owner = None
        from desktop.usage_sync import UsageSync

        self.usage_sync = UsageSync(self, autostart=sync)
        from desktop.reminders import Reminders

        self.reminders = Reminders(self, autostart=sync)

    def backend(self, route, access, payload=None):
        request = Request(
            self.api + route,
            headers={'Authorization': 'Bearer ' + access, 'Content-Type': 'application/json'},
            data=json.dumps(payload).encode() if payload is not None else None,
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=8) as response:
                return json.load(response) if response.status != 204 else None
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise DesktopError(
                'Нэвтрэлт эсвэл зөвшөөрлөө шалгана уу.' if code in (401, 403) else 'Сервер хүсэлтийг хүлээж авсангүй.',
                code if code in (400, 401, 403, 409, 429) else 502,
            ) from exc
        except (URLError, OSError, ValueError) as exc:
            raise DesktopError('Локал сервертэй холбогдож чадсангүй. Дахин оролдоно уу.', 502) from exc

    def authenticate(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer ') or len(authorization) > 4096:
            raise DesktopError('Эхлээд нэвтэрнэ үү.', 401)
        access = authorization[7:]
        return self.backend('/api/users/me/', access), access

    def _running(self, name):
        return name in self.processes and self.processes[name].poll() is None

    def state(self, user):
        from desktop.usage_sync import usage_scope

        linked = bool(self.owner and self.owner.get('user_id') == user['id'])
        camera = self.processes.get('camera')
        camera_code = camera.poll() if linked and camera is not None else None
        return {
            'available': True,
            'platform': platform.system(),
            'linked': linked,
            'launcher_started_at': self.started_at,
            'launcher_uptime_seconds': max(0, time.time() - self.started_at),
            'launcher_usage': {
                **self.usage.snapshot(usage_scope(self.api, user['id'])),
                'sync_error': self.usage_sync.error if linked else 'unlinked',
                'last_upload': self.usage_sync.last_upload if linked else None,
            },
            'another_account': not linked and any(self._running(name) for name in self.processes),
            'username': user['username'] if linked else None,
            'device_name': self.owner.get('device_name') if linked else None,
            'computer_running': linked and self._running('agent'),
            'camera_running': linked and self._running('camera'),
            'paused': is_paused(self.control) if linked else True,
            'camera_ready': all(
                importlib.util.find_spec(module) is not None for module in ('cv2', 'ultralytics', 'yaml')
            ),
            'preparing_camera': self.preparing,
            'reminders_enabled': self.reminders.enabled,
            'reminder': self.reminders.current() if linked else None,
            'camera_setup_error': self.setup_error,
            'camera_error': 'permission'
            if camera_code == 77
            else 'setup'
            if camera_code in (70, 78)
            else 'startup'
            if camera_code == 76
            else '',
            'errors': [name for name, process in self.processes.items() if linked and process.poll() not in (None, 0)],
        }

    def _spawn(self, name, command):
        from worktrack import spawn

        stream = (self.runtime / (name + '.log')).open('a')
        self.logs.append(stream)
        return spawn(
            command,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={**os.environ, 'YOLO_CONFIG_DIR': str(self.runtime / 'ultralytics')},
        )

    def _client(self, user):
        if not self.owner or self.owner.get('user_id') != user['id']:
            raise DesktopError('Эхлээд энэ төхөөрөмжийг өөрийн бүртгэлтэй холбоно уу.', 409)
        client = ApiClient(self.api, self.tokens)
        try:
            actual = client.get('/api/users/me/')
        except AgentError as exc:
            raise DesktopError(
                'Төхөөрөмжийн нэвтрэлт дууссан. «Төхөөрөмжийн нэмэлт үйлдэл» → «Дахин холбох» дарна уу.', 409
            ) from exc
        if actual['id'] != user['id']:
            raise DesktopError(
                'Энэ төхөөрөмж өөр хэрэглэгчтэй холбогдсон байна. «Дахин холбох»-оор өөрийн бүртгэлтэй холбоно уу.', 409
            )
        return client

    def _require_consent(self, user):
        client = self._client(user)
        if not client.get('/api/consents/status/')['active']:
            raise DesktopError(
                'Мэдээлэл бүртгэх зөвшөөрөл цуцлагдсан байна. «Дахин холбох»-оор дахин зөвшөөрнө үү.', 409
            )

    def _stop_collectors(self):
        set_paused(True, self.control)
        for name in ('camera', 'agent'):
            process = self.processes.pop(name, None)
            if process is not None:
                self.stop(process)

    def _prepare_camera(self):
        try:
            with self.lock:
                if self.closed:
                    return
                self.install_process = self.spawn(
                    'camera-setup', [self.python, '-m', 'pip', 'install', '-r', 'requirements-camera.txt']
                )
                process = self.install_process
            code = process.wait(timeout=600)
            with self.lock:
                self.setup_error = code != 0
        except (OSError, subprocess.TimeoutExpired):
            with self.lock:
                self.setup_error = True
                if self.install_process:
                    self.stop(self.install_process)
        finally:
            with self.lock:
                self.preparing = False

    def act(self, user, access, action, data):
        with self.lock:
            if self.closed:
                raise DesktopError('WorkTrack хаагдаж байна.', 409)
            if action == 'connect':
                if any(self._running(name) for name in self.processes):
                    raise DesktopError('Эхлээд «Ажил дуусгах» дарна уу.', 409)
                if set(data) - {'device_name', 'consent'} or data.get('consent') is not True:
                    raise DesktopError('Мэдээлэл бүртгэх зөвшөөрлөө сонгоно уу.')
                name = data.get('device_name', '')
                if not isinstance(name, str) or not name.strip() or len(name) > 120:
                    raise DesktopError('Төхөөрөмжийн нэрээ 1–120 тэмдэгтээр оруулна уу.')
                linked = self.backend(
                    '/api/desktop/link/',
                    access,
                    {'name': name.strip(), 'platform': platform.system(), 'consent': True, 'policy_version': '2026-11'},
                )
                save_tokens(self.tokens, {'access': linked['access'], 'refresh': linked['refresh']})
                try:
                    config = json.loads(self.config.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    config = json.loads((self.root / 'agent/config.example.json').read_text(encoding='utf-8'))
                config.update(api_url=self.api, username=linked['username'], device_id=linked['device_id'])
                atomic_json_write(self.config, config)
                self.owner = {'user_id': linked['user_id'], 'device_name': name.strip()}
                from desktop.usage_sync import usage_scope

                self.usage.bind(usage_scope(self.api, linked['user_id']), linked['device_id'])
                self.usage_sync.last_upload, self.usage_sync.error = None, ''
                atomic_json_write(self.metadata, self.owner)
                set_paused(True, self.control)
            else:
                if data:
                    raise DesktopError('Энэ үйлдэлд нэмэлт утга хэрэггүй.')
                if not self.owner or self.owner.get('user_id') != user['id']:
                    raise DesktopError('Өөр хэрэглэгчийн төхөөрөмжийг удирдах эрхгүй.', 403)
                if action in ('start', 'resume', 'camera-on'):
                    self._require_consent(user)
                if action == 'start':
                    set_paused(False, self.control)
                    if not self._running('agent'):
                        self.processes['agent'] = self.spawn('agent', [self.python, '-u', 'agent/main.py'])
                elif action == 'pause':
                    set_paused(True, self.control)
                elif action == 'resume':
                    if not self._running('agent'):
                        raise DesktopError('Эхлээд ажил эхлүүлнэ үү.', 409)
                    set_paused(False, self.control)
                elif action == 'stop':
                    self._stop_collectors()
                elif action == 'camera-on':
                    if not self._running('agent') or is_paused(self.control):
                        raise DesktopError('Эхлээд ажлаа эхлүүлэх буюу үргэлжлүүлнэ үү.', 409)
                    if self.preparing or not self.state(user)['camera_ready']:
                        raise DesktopError('Эхлээд «Камер бэлтгэх» дарна уу.', 409)
                    if not self._running('camera'):
                        self.processes['camera'] = self.spawn(
                            'camera', [self.python, '-u', 'main.py', '--mode', 'presence', '--consent']
                        )
                elif action == 'camera-off':
                    process = self.processes.pop('camera', None)
                    if process is not None:
                        self.stop(process)
                elif action == 'prepare-camera':
                    if self._running('camera'):
                        raise DesktopError('Эхлээд камераа унтраана уу.', 409)
                    if not self.preparing:
                        self.preparing, self.setup_error = True, False
                        threading.Thread(target=self._prepare_camera, name='camera-setup', daemon=True).start()
                elif action == 'disconnect':
                    self._stop_collectors()
                    self.usage.bind()
                    self._client(user).logout()
                    self.metadata.unlink(missing_ok=True)
                    self.owner = None
                elif action in ('reminders-on', 'reminders-off'):
                    self.reminders.set_enabled(action == 'reminders-on')
                elif action == 'quit':
                    self._stop_collectors()
                    threading.Timer(0.3, self.shutdown).start()
                else:
                    raise DesktopError('Танигдаагүй үйлдэл.', 404)
            return self.state(user)

    def close(self):
        self.usage_sync.close()
        self.reminders.close()
        with self.lock:
            self.closed = True
            if self.owns_usage:
                self.usage.close()
            if self.processes:
                self._stop_collectors()
            if self.install_process:
                self.stop(self.install_process)
            for stream in self.logs:
                stream.close()


class DesktopServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, controller, origins):
        self.controller, self.origins = controller, set(origins)
        super().__init__(address, DesktopHandler)

    def start(self):
        self.thread = threading.Thread(target=self.serve_forever, name='desktop-control', daemon=True)
        self.thread.start()

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=3)


class DesktopHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log URLs, bearer tokens or submitted values.

    def _reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A browser may cancel a status poll while navigating away.

    def _handle(self, post=False):
        try:
            port = self.server.server_port
            if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                raise DesktopError('Local host шаардлагатай.', 403)
            origin = self.headers.get('Origin')
            if (origin and origin not in self.server.origins) or (post and not origin):
                raise DesktopError('Энэ хуудас WorkTrack-ийг удирдах эрхгүй.', 403)
            if self.headers.get('X-WorkTrack-Desktop') != '1':
                raise DesktopError('Local control header шаардлагатай.', 403)
            controller = self.server.controller
            user, access = controller.authenticate(self.headers.get('Authorization'))
            if not post:
                if self.path != '/desktop/status/':
                    raise DesktopError('Олдсонгүй.', 404)
                with controller.lock:
                    result = controller.state(user)
            else:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or self.headers.get(
                    'Transfer-Encoding'
                ):
                    raise DesktopError('JSON хүсэлт шаардлагатай.', 415)
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise DesktopError('Буруу хүсэлт.')
                if not 0 < length <= 8192:
                    raise DesktopError('Хүсэлт хэт том эсвэл хоосон.', 413)
                try:
                    data = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError):
                    raise DesktopError('Буруу JSON.')
                if not isinstance(data, dict):
                    raise DesktopError('JSON object шаардлагатай.')
                actions = {
                    'connect',
                    'start',
                    'pause',
                    'resume',
                    'stop',
                    'camera-on',
                    'camera-off',
                    'prepare-camera',
                    'disconnect',
                    'reminders-on',
                    'reminders-off',
                    'quit',
                }
                action = self.path.removeprefix('/desktop/').removesuffix('/')
                if action not in actions:
                    raise DesktopError('Олдсонгүй.', 404)
                result = controller.act(user, access, action, data)
            self._reply(200, result)
        except DesktopError as exc:
            self._reply(exc.status, {'detail': str(exc)})
        except (AgentError, OSError, ValueError, KeyError):
            self._reply(503, {'detail': 'Үйлдэл амжилтгүй. WorkTrack-аа дахин нээх эсвэл дахин холбоно уу.'})

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle(True)

    def do_OPTIONS(self):
        self._reply(403, {'detail': 'Cross-origin control disabled.'})
