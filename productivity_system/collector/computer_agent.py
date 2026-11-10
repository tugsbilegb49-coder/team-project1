"""
Computer activity collector (Windows).

Hadgalah zuil: tovshiltiin too, idevhtei/idevhgui hugatsaa, program-iin ner.
HADGALAHGUI zuil: bichsen text, dalgetsiin zurag.

Ajilluulah:  python -m collector.computer_agent <employee_id>
"""
import ctypes
import os
import sys
import threading
import time
from datetime import date

import django
import psutil
from pynput import keyboard, mouse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.consent import has_consent  # noqa: E402
from core.models import ComputerActivity  # noqa: E402

FLUSH_EVERY = 60      # sekund
IDLE_AFTER = 5        # sekund

lock = threading.Lock()
state = {"keys": 0, "clicks": 0, "last_input": time.time()}


def on_key(_key):
    with lock:  # zuvhun tooluur, ali tovch ve gedgiig hadgalahgui
        state["keys"] += 1
        state["last_input"] = time.time()


def on_click(_x, _y, _button, pressed):
    if pressed:
        with lock:
            state["clicks"] += 1
            state["last_input"] = time.time()


def foreground_app():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def main(employee_id):
    if not has_consent(employee_id, "computer"):
        print("Zuvshuurul baihgui. Data tsugluulahgui.")
        return

    keyboard.Listener(on_press=on_key).start()
    mouse.Listener(on_click=on_click).start()
    print(f"Collector ehelle (employee_id={employee_id}). Ctrl+C = zogsoh.")

    active = idle = 0
    last_flush = time.time()
    app = ""
    try:
        while True:
            time.sleep(1)
            with lock:
                is_idle = time.time() - state["last_input"] > IDLE_AFTER
            if is_idle:
                idle += 1
            else:
                active += 1
                app = foreground_app() or app

            if time.time() - last_flush >= FLUSH_EVERY:
                with lock:
                    keys, clicks = state["keys"], state["clicks"]
                    state["keys"] = state["clicks"] = 0
                ComputerActivity.objects.create(
                    employee_id=employee_id, date=date.today(),
                    active_seconds=active, idle_seconds=idle,
                    key_count=keys, click_count=clicks, app_name=app[:100],
                )
                active = idle = 0
                last_flush = time.time()
    except KeyboardInterrupt:
        print("Zogsloo.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Ashiglalt: python -m collector.computer_agent <employee_id>")
        sys.exit(1)
    main(int(sys.argv[1]))
