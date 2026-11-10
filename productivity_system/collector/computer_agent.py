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
from django.db import transaction

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


def flush_activity(employee_id, active_by_app, idle_seconds, key_count, click_count):
    """Persist one interval with active time attributed to each foreground app."""
    unknown_active = active_by_app.get("", 0)
    records = [
        ComputerActivity(
            employee_id=employee_id,
            date=timezone.localdate(),
            active_seconds=seconds,
            app_name=application[:100],
        )
        for application, seconds in active_by_app.items()
        if application and seconds
    ]
    if unknown_active or idle_seconds or key_count or click_count or not records:
        records.append(
            ComputerActivity(
                employee_id=employee_id,
                date=timezone.localdate(),
                active_seconds=unknown_active,
                idle_seconds=idle_seconds,
                key_count=key_count,
                click_count=click_count,
                app_name="",
            )
        )
    if records:
        with transaction.atomic():
            ComputerActivity.objects.bulk_create(records)


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

    active_by_app = {}
    idle = 0
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
                app = foreground_app() or app
                active_by_app[app] = active_by_app.get(app, 0) + 1

            if now - last_flush >= FLUSH_EVERY:
                with lock:
                    keys, clicks = state["keys"], state["clicks"]
                    state["keys"] = state["clicks"] = 0
                try:
                    flush_activity(employee_id, active_by_app, idle, keys, clicks)
                except Exception:
                    with lock:
                        state["keys"] += keys
                        state["clicks"] += clicks
                    raise
                active_by_app.clear()
                idle = 0
                last_flush = time.monotonic()
    except KeyboardInterrupt:
        print("Zogsloo.")
    finally:
        keyboard_listener.stop()
        mouse_listener.stop()
        with lock:
            keys, clicks = state["keys"], state["clicks"]
            state["keys"] = state["clicks"] = 0
        if active_by_app or idle or keys or clicks:
            flush_activity(employee_id, active_by_app, idle, keys, clicks)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Ashiglalt: python -m collector.computer_agent <employee_id>")
        sys.exit(1)
    try:
        employee_id = int(sys.argv[1])
    except ValueError:
        print("employee_id buhel too baih yostoi.")
        sys.exit(2)
    if employee_id <= 0:
        print("employee_id eyreg too baih yostoi.")
        sys.exit(2)
    main(employee_id)
