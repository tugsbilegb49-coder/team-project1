"""pynput listener + idle timer + psutil app collector (Өдөр 3).

Нууцлал: listener callback-ууд товчлуур (key) болон координатыг (x, y) ХАРАХГҮЙ,
зөвхөн "ямар нэг input болсон" гэдгийг тоолж, сүүлийн input-ийн цагийг шинэчилнэ.
"""

import ctypes
import sys
import threading
import time
from collections import defaultdict

import psutil

# Tick хооронд ийм удаан зай гарвал компьютер sleep/hibernate хийсэн гэж үзээд тоолохгүй.
SLEEP_GAP_SECONDS = 10


def get_foreground_app():
    """Идэвхтэй цонхны процессын нэр (жишээ: 'chrome.exe'). Цонхны гарчгийг авахгүй."""
    try:
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "unknown"
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return psutil.Process(pid.value).name().lower()
        if sys.platform == "darwin":
            from AppKit import NSWorkspace  # pip install pyobjc-framework-Cocoa
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return app.localizedName() if app else "unknown"
    except Exception:
        return "unknown"
    return "unknown"


class ActivityCollector:
    def __init__(self, idle_threshold_seconds, clock=time.monotonic, app_resolver=get_foreground_app):
        self.idle_threshold = idle_threshold_seconds
        self.clock = clock
        self.app_resolver = app_resolver
        self._lock = threading.Lock()
        self._listeners = []
        now = clock()
        self._last_input = now
        self._last_tick = now
        self._reset()

    def _reset(self):
        self.active_seconds = 0.0
        self.idle_seconds = 0.0
        self.keyboard_events = 0
        self.mouse_events = 0
        self.apps = defaultdict(float)

    # --- input events (pynput thread) ---

    def on_keyboard(self, *_ignored):
        with self._lock:
            self.keyboard_events += 1
            self._last_input = self.clock()

    def on_mouse(self, *_ignored):
        with self._lock:
            self.mouse_events += 1
            self._last_input = self.clock()

    def on_mouse_move(self, *_ignored):
        # Хөдөлгөөн маш олон event үүсгэдэг тул тоолохгүй, зөвхөн idle timer-г шинэчилнэ.
        with self._lock:
            self._last_input = self.clock()

    def start_listeners(self):
        from pynput import keyboard, mouse

        kb = keyboard.Listener(on_press=self.on_keyboard)
        ms = mouse.Listener(on_click=self._on_click, on_scroll=self.on_mouse, on_move=self.on_mouse_move)
        for listener in (kb, ms):
            listener.daemon = True
            listener.start()
        self._listeners = [kb, ms]

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self.on_mouse()

    def stop_listeners(self):
        for listener in self._listeners:
            listener.stop()
        self._listeners = []

    def listeners_alive(self):
        return all(listener.is_alive() for listener in self._listeners)

    # --- main loop ---

    def is_idle(self):
        with self._lock:
            return self.clock() - self._last_input >= self.idle_threshold

    def tick(self):
        """Секунд тутам дуудна: өнгөрсөн хугацааг active эсвэл idle-д нэмнэ."""
        now = self.clock()
        app = self.app_resolver()
        with self._lock:
            elapsed = now - self._last_tick
            self._last_tick = now
            if elapsed <= 0 or elapsed > SLEEP_GAP_SECONDS:
                return
            if now - self._last_input < self.idle_threshold:
                self.active_seconds += elapsed
                self.apps[app] += elapsed
            else:
                self.idle_seconds += elapsed

    def flush(self):
        """Одоогийн тоолуурыг буцааж, тэглэнэ."""
        with self._lock:
            stats = {
                "active_seconds": self.active_seconds,
                "idle_seconds": self.idle_seconds,
                "keyboard_events": self.keyboard_events,
                "mouse_events": self.mouse_events,
                "apps": dict(self.apps),
            }
            self._reset()
        return stats
