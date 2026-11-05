"""Test computer дээр OS permission болон орчин шалгах (Өдөр 1)."""

import os
import sys
import time
import urllib.error
import urllib.request


def _result(ok, name, detail=""):
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def run_checks(config):
    results = []
    results.append(_result(sys.version_info >= (3, 9), "Python >= 3.9", sys.version.split()[0]))

    try:
        import psutil
        count = len(psutil.pids())
        results.append(_result(True, "psutil", f"{count} process харагдаж байна"))
    except Exception as e:
        results.append(_result(False, "psutil", str(e)))

    try:
        from pynput import keyboard, mouse
        listeners = [keyboard.Listener(on_press=lambda *_: None), mouse.Listener(on_click=lambda *_: None)]
        for listener in listeners:
            listener.start()
        time.sleep(0.5)
        alive = all(listener.is_alive() for listener in listeners)
        for listener in listeners:
            listener.stop()
        hint = ""
        if not alive and sys.platform == "darwin":
            hint = "System Settings > Privacy & Security > Accessibility, Input Monitoring-д Terminal/Python-г зөвшөөрнө үү"
        results.append(_result(alive, "pynput keyboard/mouse listener", hint))
    except Exception as e:
        hint = str(e)
        if sys.platform.startswith("linux"):
            hint += " (Linux дээр X11 session хэрэгтэй, Wayland дэмжигдэхгүй)"
        results.append(_result(False, "pynput keyboard/mouse listener", hint))

    from collector import get_foreground_app
    app = get_foreground_app()
    results.append(_result(app != "unknown", "Foreground app detection", app))

    spool_dir = os.path.dirname(config["spool_file"])
    try:
        os.makedirs(spool_dir, exist_ok=True)
        probe = os.path.join(spool_dir, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        results.append(_result(True, "Spool folder бичих эрх", spool_dir))
    except OSError as e:
        results.append(_result(False, "Spool folder бичих эрх", str(e)))

    # API ажиллахгүй байсан ч agent spool-д хадгална, тиймээс энэ нь зөвхөн анхааруулга.
    health_url = config["api_url"].rsplit("/api/", 1)[0] + "/health"
    try:
        with urllib.request.urlopen(health_url, timeout=3) as r:
            _result(r.status == 200, "API холболт", health_url)
    except (urllib.error.URLError, OSError) as e:
        _result(False, "API холболт (анхааруулга)", f"{health_url}: {e}")

    ok = all(results)
    print("\nБүх шалгалт амжилттай." if ok else "\nДээрх FAIL-уудыг засна уу (README-ийн Troubleshooting).")
    return ok
