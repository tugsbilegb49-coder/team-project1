#!/usr/bin/env python3
"""macOS and Windows foreground-application collector for Worker Activity Monitor.

The agent records only application name, category, start time and duration.
It intentionally does not inspect keystrokes, screen contents, window titles,
documents, browser URLs or browsing history.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from getpass import getpass
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import math
import threading
from typing import Any

if __package__:
    from .intervals import split_interval
else:
    from intervals import split_interval
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = AGENT_DIR / "config.json"
DEFAULT_TOKEN_PATH = AGENT_DIR / ".agent_tokens.json"
DEFAULT_QUEUE_PATH = AGENT_DIR / ".pending_events.json"
DEFAULT_CONTROL_PATH = AGENT_DIR / "control.json"
BROWSERS = {"Safari", "Google Chrome", "Chromium", "Firefox", "Arc", "Microsoft Edge"}
COMMUNICATION_APPS = {"Slack", "Microsoft Teams", "Zoom", "Discord"}
IDLE_APPLICATION = "Idle"
WINDOWS_PROCESS_NAMES = {
    "code": "Visual Studio Code",
    "devenv": "Visual Studio",
    "pycharm": "PyCharm",
    "pycharm64": "PyCharm",
    "idea64": "IntelliJ IDEA",
    "winword": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpnt": "Microsoft PowerPoint",
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    "firefox": "Firefox",
    "slack": "Slack",
    "teams": "Microsoft Teams",
    "zoom": "Zoom",
    "notepad": "Notepad",
    "explorer": "Windows Explorer",
}


class AgentError(RuntimeError):
    pass


class ApiError(AgentError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AgentError(
            f"Configuration file not found: {path}. "
            "Copy agent/config.example.json to agent/config.json and set your username."
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentError(f"Configuration is not valid JSON: {path}") from exc

    if not isinstance(config.get("api_url"), str) or not config["api_url"].strip():
        raise AgentError("config.json needs a non-empty api_url.")
    if not isinstance(config.get("username"), str) or not config["username"].strip():
        raise AgentError("config.json needs the employee username.")
    interval = config.get("interval_seconds", 30)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or not 5 <= interval <= 3600:
        raise AgentError("interval_seconds must be between 5 and 3600 seconds.")
    poll = config.get("poll_interval_seconds", 1)
    if isinstance(poll, bool) or not isinstance(poll, (int, float)) or not math.isfinite(poll) or not 0.1 <= poll <= 5:
        raise AgentError("poll_interval_seconds must be between 0.1 and 5 seconds.")
    gap = config.get("max_sample_gap_seconds", 10)
    if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not math.isfinite(gap) or not poll < gap <= 300:
        raise AgentError("max_sample_gap_seconds must exceed poll_interval_seconds and be at most 300.")
    config["max_sample_gap_seconds"] = float(gap)
    config["poll_interval_seconds"] = float(poll)
    config["api_url"] = config["api_url"].rstrip("/")
    config["interval_seconds"] = float(interval)
    idle_threshold = config.get("idle_threshold_seconds", 300)
    if not isinstance(idle_threshold, (int, float)) or idle_threshold < 30:
        raise AgentError("idle_threshold_seconds must be a number of at least 30 seconds.")
    config["idle_threshold_seconds"] = float(idle_threshold)
    config["productive_apps"] = config.get("productive_apps", [])
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    """Persist non-secret agent settings such as the enrolled device ID."""
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(items), encoding="utf-8")
    temporary_path.replace(path)


def is_paused(path: Path = DEFAULT_CONTROL_PATH) -> bool:
    if not path.is_file():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("paused", False))
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def set_paused(paused: bool, path: Path = DEFAULT_CONTROL_PATH) -> None:
    path.write_text(json.dumps({"paused": paused}) + "\n", encoding="utf-8")


def _macos_foreground_application() -> str:
    """Return the macOS frontmost application's name without examining its content."""
    script = (
        'tell application "System Events"\n'
        "  set frontApp to name of first application process whose frontmost is true\n"
        "end tell\n"
        "return frontApp"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentError(
            "Could not read the active application. Allow Terminal or VS Code to automate "
            "System Events in macOS Privacy & Security settings, then try again."
        ) from exc
    app_name = result.stdout.strip()
    if not app_name:
        raise AgentError("macOS did not return an active application name.")
    return app_name


def _macos_idle_seconds() -> float:
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"], text=True, capture_output=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentError("Could not read macOS idle time.") from exc
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout)
    if not match:
        raise AgentError("macOS did not return an idle-time value.")
    return int(match.group(1)) / 1_000_000_000


def display_name_for_windows_process(process_name: str) -> str:
    """Normalise common executable names without retaining the full executable path."""
    return WINDOWS_PROCESS_NAMES.get(process_name.casefold(), process_name)


def _windows_foreground_application() -> str:
    """Return the foreground program's executable name, never its window title.

    Window titles often contain document or file names. Querying the foreground
    process executable instead avoids collecting that content.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    window = user32.GetForegroundWindow()
    if not window:
        raise AgentError("Windows did not return a foreground application.")

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    process = kernel32.OpenProcess(0x1000, False, process_id.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        raise AgentError("Windows denied access to the foreground application name.")

    try:
        path_buffer = ctypes.create_unicode_buffer(32768)
        path_size = wintypes.DWORD(len(path_buffer))
        if not kernel32.QueryFullProcessImageNameW(process, 0, path_buffer, ctypes.byref(path_size)):
            raise AgentError("Windows could not read the foreground application name.")
        executable_name = Path(path_buffer.value).stem
        if not executable_name:
            raise AgentError("Windows returned an empty foreground application name.")
        return display_name_for_windows_process(executable_name)
    finally:
        kernel32.CloseHandle(process)


def _windows_idle_seconds() -> float:
    import ctypes
    from ctypes import wintypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LastInputInfo)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
    kernel32.GetTickCount.restype = wintypes.DWORD
    info = LastInputInfo(ctypes.sizeof(LastInputInfo), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        raise AgentError("Windows could not read idle time.")
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def foreground_application() -> str:
    """Return the supported operating system's frontmost program name."""
    operating_system = platform.system()
    if operating_system == "Darwin":
        return _macos_foreground_application()
    if operating_system == "Windows":
        return _windows_foreground_application()
    raise AgentError("This desktop agent currently supports macOS and Windows only.")


def idle_seconds() -> float:
    """Return elapsed seconds since the last user input without recording that input."""
    operating_system = platform.system()
    if operating_system == "Darwin":
        return _macos_idle_seconds()
    if operating_system == "Windows":
        return _windows_idle_seconds()
    raise AgentError("This desktop agent currently supports macOS and Windows only.")


def application_for_idle_state(application: str, elapsed_idle_seconds: float, threshold_seconds: float) -> str:
    return IDLE_APPLICATION if elapsed_idle_seconds >= threshold_seconds else application


def category_for(application: str, productive_apps: list[Any]) -> str:
    configured_work_apps = {str(item).casefold() for item in productive_apps}
    app_key = application.casefold()
    if app_key in configured_work_apps:
        return "WORK"
    if application in BROWSERS:
        return "BROWSER"
    if application in COMMUNICATION_APPS:
        return "COMMUNICATION"
    return "OTHER"


class ApiClient:
    def __init__(self, api_url: str, token_path: Path):
        self.api_url = api_url
        self.token_path = token_path

    def _post_json(self, route: str, payload: dict[str, Any], access_token: str | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = Request(
            f"{self.api_url}{route}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status == 204:
                    return {}
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ApiError(exc.code, f"API request failed ({exc.code}): {body}") from exc
        except (URLError, TimeoutError) as exc:
            raise AgentError(f"Could not reach Django API at {self.api_url}: {exc}") from exc

    def _read_tokens(self) -> dict[str, str]:
        if not self.token_path.is_file():
            raise AgentError("No desktop-agent login found. Run: python3 agent/main.py --login")
        try:
            tokens = json.loads(self.token_path.read_text(encoding="utf-8"))
            if not tokens.get("access") or not tokens.get("refresh"):
                raise ValueError("missing access or refresh token")
            return tokens
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AgentError("The saved desktop-agent login is invalid. Run --login again.") from exc

    def _write_tokens(self, tokens: dict[str, str]) -> None:
        temporary_path = self.token_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(tokens), encoding="utf-8")
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(self.token_path)
        os.chmod(self.token_path, 0o600)

    def login(self, username: str, password: str) -> None:
        tokens = self._post_json("/api/auth/login/", {"username": username, "password": password})
        if not tokens.get("access") or not tokens.get("refresh"):
            raise AgentError("Login response did not contain JWT tokens.")
        self._write_tokens(tokens)

    def logout(self) -> None:
        tokens = self._read_tokens()
        self._authenticated_post("/api/auth/logout/", {"refresh": tokens["refresh"]})
        self.token_path.unlink(missing_ok=True)

    def _refresh_access_token(self, tokens: dict[str, str]) -> dict[str, str]:
        refreshed = self._post_json("/api/auth/refresh/", {"refresh": tokens["refresh"]})
        if not refreshed.get("access"):
            raise AgentError("The saved login has expired. Run --login again.")
        tokens["access"] = refreshed["access"]
        self._write_tokens(tokens)
        return tokens

    def _authenticated_post(self, route: str, payload: dict[str, Any]) -> dict[str, Any]:
        tokens = self._read_tokens()
        try:
            return self._post_json(route, payload, tokens["access"])
        except ApiError as exc:
            if exc.status != 401:
                raise
            tokens = self._refresh_access_token(tokens)
            return self._post_json(route, payload, tokens["access"])

    def enroll_device(self, name: str, platform_name: str) -> dict[str, Any]:
        return self._authenticated_post("/api/devices/enroll/", {"name": name, "platform": platform_name})

    def grant_consent(self, policy_version: str) -> dict[str, Any]:
        return self._authenticated_post("/api/consents/grant/", {"policy_version": policy_version})

    def revoke_consent(self) -> dict[str, Any]:
        return self._authenticated_post("/api/consents/revoke/", {})

    def ingest(self, payload: dict[str, Any]) -> None:
        self._authenticated_post("/api/computer-activity/ingest/", payload)


def segment_payload(application: str, category: str, started_at: datetime, ended_at: datetime) -> dict[str, Any] | None:
    duration = (ended_at - started_at).total_seconds()
    if duration <= 0:
        return None
    return {
        "application": application,
        "category": category,
        "started_at": started_at.isoformat(),
        "duration_seconds": duration,
    }


class PendingUploader:
    """Persist segments immediately; perform slow network I/O off the sampling loop."""

    def __init__(self, client: ApiClient, path: Path = DEFAULT_QUEUE_PATH):
        self.client, self.path = client, path
        self.pending = _read_json_list(path)
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="activity-upload", daemon=True)

    def start(self):
        self.thread.start()
        self.request_flush()  # Retry any queue left by the previous run.

    def append(self, payload):
        with self.lock:
            self.pending.append(payload)
            _write_json_list(self.path, self.pending)

    def request_flush(self):
        self.ready.set()

    def _run(self):
        while True:
            self.ready.wait()
            self.ready.clear()
            try:
                while True:
                    with self.lock:
                        payload = self.pending[0] if self.pending else None
                    if payload is None:
                        break
                    self.client.ingest(payload)
                    with self.lock:
                        self.pending.pop(0)
                        _write_json_list(self.path, self.pending)
            except (AgentError, OSError) as exc:
                print(f"Upload paused; queue retained: {exc}", file=sys.stderr)
            if self.stopping.is_set():
                return

    def stop(self):
        self.stopping.set()
        self.ready.set()
        self.thread.join(timeout=5)
        # Any in-flight request is replay-safe; unsent rows remain on disk.


def _now():
    return datetime.now().astimezone()


def run_agent(config: dict[str, Any], client: ApiClient) -> None:
    current_application = None
    segment_started_at = None
    last_observed_at = None
    last_observed_tick = None
    recorded_until = None
    uploader = PendingUploader(client)
    uploader.start()
    last_upload = time.monotonic()
    poll_interval = config.get("poll_interval_seconds", 1)
    max_gap = config.get("max_sample_gap_seconds", 10)
    print(f"Desktop agent started: sample every {poll_interval}s, upload every {config['interval_seconds']}s.")
    print("Only application name, category and duration are sent. Ctrl+C stops collection.")

    def close_segment(end):
        nonlocal recorded_until
        if current_application is None or segment_started_at is None:
            return
        for start, finish in split_interval(segment_started_at, end):
            payload = segment_payload(current_application,
                category_for(current_application, config["productive_apps"]), start, finish)
            if config.get("device_id"):
                payload["device_id"] = config["device_id"]
            uploader.append(payload)
            recorded_until = finish

    try:
        while True:
            tick_started = time.monotonic()
            if is_paused():
                if last_observed_at is not None:
                    close_segment(last_observed_at)
                current_application = segment_started_at = last_observed_at = last_observed_tick = None
                # Retry previously recorded segments without collecting paused time.
            else:
                try:
                    next_application = application_for_idle_state(
                        foreground_application(), idle_seconds(), config["idle_threshold_seconds"])
                    observed_at = _now()
                    observed_tick = time.monotonic()
                    if last_observed_at is not None:
                        wall_gap = (observed_at - last_observed_at).total_seconds()
                        monotonic_gap = observed_tick - last_observed_tick
                        if wall_gap <= 0 or wall_gap > max_gap or monotonic_gap > max_gap or abs(wall_gap - monotonic_gap) > 2:
                            close_segment(last_observed_at)
                            current_application = segment_started_at = last_observed_at = last_observed_tick = None
                            print("Sleep/clock gap skipped; starting a new observation.")
                    # A backwards clock must catch up with already persisted rows.
                    if recorded_until is not None and observed_at < recorded_until:
                        current_application = segment_started_at = last_observed_at = last_observed_tick = None
                        time.sleep(poll_interval)
                        continue
                    if current_application is None:
                        segment_started_at = observed_at
                    elif next_application != current_application:
                        close_segment(observed_at)
                        segment_started_at = observed_at
                    current_application = next_application
                    last_observed_at = observed_at
                    last_observed_tick = observed_tick
                except AgentError as exc:
                    if last_observed_at is not None:
                        close_segment(last_observed_at)
                    current_application = segment_started_at = last_observed_at = last_observed_tick = None
                    print(f"Active-app lookup failed; unobserved time skipped: {exc}", file=sys.stderr)

            if time.monotonic() - last_upload >= config["interval_seconds"]:
                if last_observed_at is not None:
                    close_segment(last_observed_at)
                    segment_started_at = last_observed_at
                uploader.request_flush()
                last_upload = time.monotonic()
            time.sleep(max(0, poll_interval - (time.monotonic() - tick_started)))
    except KeyboardInterrupt:
        # Stop at the last actual sample instead of guessing the app after it.
        if last_observed_at is not None and not is_paused():
            close_segment(last_observed_at)
    finally:
        uploader.stop()
        print("Desktop agent stopped. Unsent segments are retained locally.")


def main() -> None:
    parser = argparse.ArgumentParser(description="macOS and Windows foreground-application activity agent")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to agent config JSON")
    parser.add_argument("--login", action="store_true", help="Prompt for password and save the local JWT login")
    controls = parser.add_mutually_exclusive_group()
    controls.add_argument("--logout", action="store_true", help="Revoke the saved refresh token and pause local collection")
    controls.add_argument("--pause", action="store_true", help="Stop collecting and uploading new activity locally")
    controls.add_argument("--resume", action="store_true", help="Resume local collection and uploading")
    controls.add_argument("--status", action="store_true", help="Show local pause and offline-queue status")
    controls.add_argument("--grant-consent", metavar="POLICY", help="Record informed consent for a policy version")
    controls.add_argument("--revoke-consent", action="store_true", help="Revoke server-side consent and pause locally")
    args = parser.parse_args()

    try:
        if args.pause:
            set_paused(True)
            print("Desktop agent paused. No new activity will be collected locally.")
            return
        if args.resume:
            set_paused(False)
            print("Desktop agent resumed.")
            return
        if args.status:
            print(json.dumps({"paused": is_paused(), "queued_events": len(_read_json_list(DEFAULT_QUEUE_PATH))}))
            return
        config = load_config(args.config)
        client = ApiClient(config["api_url"], DEFAULT_TOKEN_PATH)
        if args.logout:
            set_paused(True)
            client.logout()
            print("Logged out. Refresh token revoked, saved login removed, local collection paused.")
            return
        if args.grant_consent:
            client.grant_consent(args.grant_consent)
            print(f"Consent granted for policy version {args.grant_consent}.")
            return
        if args.revoke_consent:
            client.revoke_consent()
            set_paused(True)
            print("Consent revoked and local monitoring paused.")
            return
        if args.login:
            password = getpass(f"Password for {config['username']}: ")
            client.login(config["username"], password)
            device = client.enroll_device(platform.node() or "Unnamed device", platform.system())
            config["device_id"] = str(device["id"])
            save_config(args.config, config)
            print("Desktop-agent login and device enrollment saved locally. Start monitoring with: python3 agent/main.py")
            return
        run_agent(config, client)
    except AgentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
