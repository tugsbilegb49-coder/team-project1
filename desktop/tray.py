"""WorkTrack's icon in the macOS menu bar / Windows notification area.

A small separate process: the launcher starts it with a secret (WORKTRACK_TRAY_SECRET) and it talks
only to the local control on 127.0.0.1:8766 (desktop/service.py, /desktop/tray/). Start, pause and
finish work, open the page or quit WorkTrack without opening the browser. The icon's colour shows
the state: green recording, amber paused, grey not started. It closes itself when WorkTrack stops.
"""

import json
import os
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = os.environ.get('WORKTRACK_TRAY_URL', 'http://127.0.0.1:8766') + '/desktop/tray/'
POLL = 2
GIVE_UP_AFTER = 20  # Seconds without the launcher before the icon goes away.
COLORS = {'working': (32, 185, 154), 'paused': (232, 152, 32), 'idle': (128, 140, 136)}


def call(action='', timeout=10):
    request = Request(
        URL + (action + '/' if action else ''),
        data=b'' if action else None,
        headers={'X-WorkTrack-Tray': os.environ.get('WORKTRACK_TRAY_SECRET', '')},
        method='POST' if action else 'GET',
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def kind(state):
    return 'working' if state.get('working') else 'paused' if state.get('paused') else 'idle'


def status_text(state):
    if state is None:
        return 'WorkTrack холбогдож байна…'
    if not state.get('linked'):
        return 'Төхөөрөмж холбогдоогүй'
    if state.get('working'):
        return f'● Бүртгэж байна · {state["task"]}' if state.get('task') else '● Бүртгэж байна (даалгаваргүй)'
    if state.get('paused'):
        return '⏸ Түр зогссон'
    return '○ Ажил эхлээгүй'


def start_label(state):
    if state and state.get('working'):
        return f'Даалгаврын цаг эхлүүлэх: {state["next_task"]}'
    if state and state.get('paused'):
        return 'Ажил үргэлжлүүлэх'
    if state and state.get('next_task'):
        return f'Ажил эхлүүлэх: {state["next_task"]}'
    return 'Ажил эхлүүлэх…'


def can_start(state):
    if not state or not state.get('linked'):
        return False
    if not state.get('working'):
        return True
    # Recording apps without a task (e.g. after sleep ended the timer): offer the remembered task.
    return not state.get('task') and state.get('next_is_task')


def image(name):
    from PIL import Image, ImageDraw

    size = 64
    picture = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    draw.ellipse((4, 4, size - 4, size - 4), fill=COLORS[name] + (255,))
    draw.ellipse((22, 22, size - 22, size - 22), fill=(255, 255, 255, 255))
    return picture


class Tray:
    def __init__(self):
        import pystray

        self.pystray = pystray
        self.state = None
        self.shown = None
        item = pystray.MenuItem
        self.icon = pystray.Icon(
            'WorkTrack',
            image('idle'),
            'WorkTrack',
            menu=pystray.Menu(
                item(lambda _: status_text(self.state), None, enabled=False),
                item(lambda _: start_label(self.state), self.action('start'), visible=lambda _: can_start(self.state)),
                item('Түр зогсоох', self.action('pause'), visible=lambda _: bool(self.state and self.state['working'])),
                item(
                    'Ажил дуусгах',
                    self.action('finish'),
                    visible=lambda _: bool(self.state and (self.state['running'] or self.state.get('task'))),
                ),
                pystray.Menu.SEPARATOR,
                item('WorkTrack хуудас нээх', self.action('open'), default=True),
                item('WorkTrack хаах', self.action('quit')),
            ),
        )

    def on_main(self, function):
        """AppKit objects may only change on the main thread; Windows does not mind."""
        if sys.platform == 'darwin':
            from PyObjCTools import AppHelper

            AppHelper.callAfter(function)
        else:
            function()

    def show(self, state):
        self.state = state
        key = json.dumps(state, sort_keys=True)
        if key == self.shown:
            return
        self.shown = key

        def apply():
            self.icon.icon = image(kind(state))
            self.icon.title = 'WorkTrack — ' + status_text(state)
            self.icon.update_menu()

        self.on_main(apply)

    def action(self, name):
        def run():
            try:
                result = call(name, timeout=60)
            except HTTPError as error:
                try:
                    message = json.load(error).get('detail') or 'Үйлдэл амжилтгүй.'
                except ValueError:
                    message = 'Үйлдэл амжилтгүй.'
                self.notify(message)
                return
            except (URLError, OSError, ValueError):
                self.notify('WorkTrack-тэй холбогдож чадсангүй.')
                return
            if result.get('message'):
                self.notify(result['message'])
            if name != 'quit':
                self.show({key: value for key, value in result.items() if key != 'message'})

        # Menu callbacks run on the UI thread: do the work beside it.
        return lambda *_: threading.Thread(target=run, name=f'tray-{name}', daemon=True).start()

    def notify(self, message):
        from desktop.reminders import notify

        notify(message)

    def poll(self):
        last_seen = time.monotonic()
        while True:
            try:
                self.show(call())
                last_seen = time.monotonic()
            except HTTPError as error:
                error.close()
                if error.code in (403, 409):  # WorkTrack is closing, or this is not our launcher.
                    reason = f'WorkTrack answered HTTP {error.code}'
                    break
            except (URLError, OSError, ValueError) as error:
                if time.monotonic() - last_seen > GIVE_UP_AFTER:
                    reason = f'WorkTrack unreachable for {GIVE_UP_AFTER} s: {error}'
                    break
            time.sleep(POLL)
        print('WorkTrack tray stopping:', reason, flush=True)
        self.on_main(self.icon.stop)

    def run(self):
        if sys.platform == 'darwin':
            import AppKit

            # No Dock icon for this helper, only the menu bar item.
            AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        def setup(icon):
            icon.visible = True
            print('WorkTrack tray ready', flush=True)
            threading.Thread(target=self.poll, name='tray-poll', daemon=True).start()

        self.icon.run(setup=setup)
        print('WorkTrack tray stopped', flush=True)


def main():
    print('WorkTrack tray starting', flush=True)
    Tray().run()


if __name__ == '__main__':
    main()
