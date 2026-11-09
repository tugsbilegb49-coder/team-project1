"""The working day as the WorkTrack program sees it, without the web page.

* Remembers the task each person last started on this computer, so the next start is one click
  (on the page or from the tray icon).
* Keeps a running task timer alive while this computer records work. The server ends a task
  session 90 seconds after the last sign of life (workforce/workflow.py LEASE_SECONDS); until now
  only an open web page gave that sign, so closing the page stopped the task time.
* Start / pause / finish for the tray icon: the same steps as the page (useWorkday.js).
"""

import json
import threading

from agent.main import AgentError, ApiClient, ApiError, is_paused
from agent.token_store import atomic_json_write

BEAT_EVERY = 30  # Well inside the server's 90-second lease.
SCHEDULE_EVERY = 20  # Beats between reads of the working schedule (10 minutes).


def parse_schedule(settings):
    """{'days': {0…6}, 'start': minutes, 'end': minutes} from /api/monitoring-settings/."""

    def minutes(value):
        hours, mins = str(value).split(':')[:2]
        return int(hours) * 60 + int(mins)

    return {
        'days': {int(day) for day in settings['work_days']},
        'start': minutes(settings['work_start']),
        'end': minutes(settings['work_end']),
    }


NO_TASK = 'none'


class Workday:
    def __init__(self, controller, autostart=True):
        self.controller = controller
        self.path = controller.runtime / 'last-task.json'
        self.session = None  # The owner's task session as the server last reported it.
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None
        if autostart:
            self.thread = threading.Thread(target=self._run, name='task-keeper', daemon=True)
            self.thread.start()

    # Remembered choice -------------------------------------------------------------------------

    def _choices(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def remembered(self, user_id):
        """{'task': 'none' | '<id>', 'title': str} last started by this person here, or None."""
        value = self._choices().get(str(user_id))
        return value if isinstance(value, dict) and isinstance(value.get('task'), str) else None

    def remember(self, user_id, task, title=''):
        if task != NO_TASK and not (task.isdigit() and len(task) <= 12):
            raise ValueError('task')
        if not isinstance(title, str) or len(title) > 300:
            raise ValueError('title')
        with self.lock:
            choices = self._choices()
            choices[str(user_id)] = {'task': task, 'title': title if task != NO_TASK else ''}
            atomic_json_write(self.path, choices)

    def forget(self, user_id):
        with self.lock:
            choices = self._choices()
            if choices.pop(str(user_id), None) is not None:
                atomic_json_write(self.path, choices)

    # Task session ------------------------------------------------------------------------------

    def _client(self):
        return ApiClient(self.controller.api, self.controller.tokens)

    def _receive(self, data):
        session = data.get('session') if isinstance(data, dict) else None
        self.session = session if isinstance(session, dict) else None
        return self.session

    def refresh(self, client=None):
        return self._receive((client or self._client()).get('/api/tasks/work-session/'))

    def recording(self):
        controller = self.controller
        return bool(controller.owner and controller._running('agent') and not is_paused(controller.control))

    def beat(self):
        """One sign of life for the running task while this computer records work."""
        if not self.recording():
            return
        try:
            client = self._client()
            session = self.session
            if session and session.get('running'):
                self._receive(client._authenticated_post('/api/tasks/work-session/', {'session_id': session['id']}))
            else:
                self.refresh(client)  # E.g. a task started on the page, which was then closed.
                if self.session and self.session.get('running'):
                    self.beat()
        except (AgentError, OSError, ValueError, KeyError):
            pass  # Offline: try again next time; the page or the next beat catches up.

    def refresh_schedule(self):
        """The working schedule for reminders (desktop/reminders.py); kept as it was when offline."""
        if not self.controller.owner:
            return
        try:
            self.controller.schedule = parse_schedule(self._client().get('/api/monitoring-settings/'))
        except (AgentError, OSError, ValueError, KeyError, TypeError):
            pass

    def _run(self):
        beats = 0
        while not self.stopping.wait(BEAT_EVERY):
            if beats % SCHEDULE_EVERY == 0:
                self.refresh_schedule()
            beats += 1
            self.beat()

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _stop_task(self, client):
        session = self.session if self.session is not None else self.refresh(client)
        if session and session.get('running'):
            self._receive(
                client._authenticated_post(f'/api/tasks/{session["task_id"]}/work-stop/', {'session_id': session['id']})
            )

    # Tray actions ------------------------------------------------------------------------------

    def owner(self):
        owner = self.controller.owner
        if not owner:
            return None
        return {'id': owner['user_id'], 'username': owner.get('username', '')}

    def start(self):
        """Start with the remembered task. Returns (message, open_page)."""
        user = self.owner()
        if not user:
            return 'Эхлээд WorkTrack хуудаснаас төхөөрөмжөө холбоно уу.', True
        choice = self.remembered(user['id'])
        if not choice:
            return 'Хийх даалгавраа хуудаснаас нэг удаа сонгоод эхлүүлнэ үү.', True
        client = self.controller._client(user)
        session = self.refresh(client)
        if choice['task'] != NO_TASK and not (session and session.get('running')):
            try:
                self._receive(client._authenticated_post(f'/api/tasks/{choice["task"]}/work-start/', {}))
            except ApiError as exc:
                if exc.status not in (400, 403, 404, 409):
                    raise
                self.forget(user['id'])
                return (
                    f'«{choice["title"]}» даалгаврыг эхлүүлэх боломжгүй (дууссан эсвэл шилжсэн). Шинээр сонгоно уу.',
                    True,
                )
        controller = self.controller
        if not controller._running('agent'):
            controller.act(user, None, 'start', {})
        elif is_paused(controller.control):
            controller.act(user, None, 'resume', {})
        return '', False

    def pause(self, finish=False):
        user = self.owner()
        if not user:
            return '', False
        self._stop_task(self.controller._client(user))
        controller = self.controller
        if finish:
            controller.act(user, None, 'stop', {})
        elif controller._running('agent'):
            controller.act(user, None, 'pause', {})
        return '', False

    def tray_state(self):
        controller = self.controller
        linked = bool(controller.owner)
        running = linked and controller._running('agent')
        paused = running and is_paused(controller.control)
        session = self.session if linked and self.session and self.session.get('running') else None
        choice = self.remembered(controller.owner['user_id']) if linked else None
        return {
            'linked': linked,
            'running': running,
            'working': running and not paused,
            'paused': paused,
            'task': session['title'] if session else None,
            'next_task': (choice['title'] or 'Даалгаваргүй') if choice else None,
            'next_is_task': bool(choice and choice['task'] != NO_TASK),
            'reminder': controller.reminders.current() if linked else None,
            'update': controller.updates.available,
        }
