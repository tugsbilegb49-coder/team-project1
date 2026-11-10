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
import django
import psutil
from pynput import keyboard, mouse
from django.utils import timezone

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.consent import has_consent  # noqa: E402
from core.models import ComputerActivity, Employee  # noqa: E402

FLUSH_EVERY = 60      # sekund
IDLE_AFTER = 5        # sekund
CONSENT_CHECK_EVERY = 5

lock = threading.Lock()
state = {"keys": 0, "clicks": 0, "last_input": time.monotonic()}


def on_key(_key):
    with lock:  # zuvhun tooluur, ali tovch ve gedgiig hadgalahgui
        state["keys"] += 1
        state["last_input"] = time.monotonic()


def on_click(_x, _y, _button, pressed):
    if pressed:
        with lock:
            state["clicks"] += 1
            state["last_input"] = time.monotonic()


def foreground_app():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def main(employee_id):
    if not Employee.objects.filter(pk=employee_id).exists():
        print(f"Employee oldsongui (id={employee_id}).")
        return
    if not has_consent(employee_id, "computer"):
        print("Zuvshuurul baihgui. Data tsugluulahgui.")
        return

    keyboard_listener = keyboard.Listener(on_press=on_key)
    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener.start()
    try:
        mouse_listener.start()
    except Exception:
        keyboard_listener.stop()
        raise
    print(f"Collector ehelle (employee_id={employee_id}). Ctrl+C = zogsoh.")

    active = idle = 0
    last_flush = time.monotonic()
    last_consent_check = last_flush
    app = ""
    try:
        while True:
            time.sleep(1)
            now = time.monotonic()
            if now - last_consent_check >= CONSENT_CHECK_EVERY:
                last_consent_check = now
                if not has_consent(employee_id, "computer"):
                    print("Computer collector-iin zuvshuurul tsutslagdlaa. Zogsloo.")
                    break
            with lock:
                is_idle = now - state["last_input"] > IDLE_AFTER
            if is_idle:
                idle += 1
            else:
                active += 1
                app = foreground_app() or app

            if now - last_flush >= FLUSH_EVERY:
                with lock:
                    keys, clicks = state["keys"], state["clicks"]
                    state["keys"] = state["clicks"] = 0
                ComputerActivity.objects.create(
                    employee_id=employee_id, date=timezone.localdate(),
                    active_seconds=active, idle_seconds=idle,
                    key_count=keys, click_count=clicks, app_name=app[:100],
                )
                active = idle = 0
                last_flush = time.monotonic()
    except KeyboardInterrupt:
        print("Zogsloo.")
    finally:
        keyboard_listener.stop()
        mouse_listener.stop()
        with lock:
            keys, clicks = state["keys"], state["clicks"]
            state["keys"] = state["clicks"] = 0
        if active or idle or keys or clicks:
            ComputerActivity.objects.create(
                employee_id=employee_id,
                date=timezone.localdate(),
                active_seconds=active,
                idle_seconds=idle,
                key_count=keys,
                click_count=clicks,
                app_name=app[:100],
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Ashiglalt: python -m collector.computer_agent <employee_id>")
        sys.exit(1)
    main(int(sys.argv[1]))
