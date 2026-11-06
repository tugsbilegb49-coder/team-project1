"""Optional Django API synchronisation for single-user camera sessions.

The webcam monitor continues to write its local CSV log even when the API is
offline. This uploader reuses the refresh token saved by agent/main.py and
never stores a password.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent.intervals import split_interval
from agent.queue_limits import bounded_queue
from agent.main import PendingUploader, AgentError, ApiError
from agent.token_store import read_tokens, save_tokens, StaleTokenError


class CameraAPISyncError(RuntimeError):
    """The local camera monitor can continue safely after a sync error."""


class CameraEventUploader:
    def __init__(self, api_url: str, token_file: str, device_config_file: str = "agent/config.json", queue_file: str = "data/.pending_camera_events.json", max_queue_events: int = 10000, max_queue_bytes: int = 10 * 1024 * 1024):
        bounded_queue([], max_queue_events, max_queue_bytes)
        self.max_queue_events, self.max_queue_bytes = max_queue_events, max_queue_bytes
        self.api_url = api_url.rstrip("/")
        self.token_file = Path(token_file)
        self.device_config_file = Path(device_config_file)
        self.queue_file = Path(queue_file)
        owner = self
        class UploadClient:
            def ingest(self, payload):
                try:
                    owner._send(payload)
                except CameraAPISyncError as exc:
                    if getattr(exc, "status", None) is not None:
                        raise ApiError(exc.status, str(exc), route=getattr(exc, "route", None)) from exc
                    raise AgentError(str(exc)) from exc
        self._worker = PendingUploader(UploadClient(), self.queue_file,
            max_events=max_queue_events, max_bytes=max_queue_bytes, event_route="/api/activity-events/ingest/")
        self._worker.start()

    def _device_id(self) -> str | None:
        try:
            return json.loads(self.device_config_file.read_text(encoding="utf-8")).get("device_id")
        except (OSError, json.JSONDecodeError, AttributeError):
            return None

    def _read_queue(self):
        with self._worker.lock:
            return list(self._worker.pending)

    def flush(self, timeout=5):
        return self._worker.flush(timeout)

    def close(self):
        return self._worker.stop()

    def _read_tokens(self) -> dict[str, str]:
        if not self.token_file.is_file():
            raise CameraAPISyncError(
                f"Agent token not found at {self.token_file}. "
                "First run: python3 agent/main.py --login"
            )
        try:
            tokens = read_tokens(self.token_file)
            if not tokens.get("access") or not tokens.get("refresh"):
                raise ValueError("missing token")
            return tokens
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CameraAPISyncError("Saved agent login is invalid. Run agent/main.py --login again.") from exc

    def _save_tokens(self, tokens, expected_refresh=None):
        try:
            save_tokens(self.token_file, tokens, expected_refresh)
        except StaleTokenError as exc:
            raise CameraAPISyncError(str(exc)) from exc

    def _post(self, route: str, payload: dict[str, Any], access_token: str | None = None) -> None:
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
            with urlopen(request, timeout=15):
                return
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            error = CameraAPISyncError(f"Django API returned {exc.code}: {message}")
            exc.close()
            error.status = exc.code
            error.route = route
            raise error from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise CameraAPISyncError(f"Could not reach Django API at {self.api_url}: {exc}") from exc

    def _refresh(self, tokens: dict[str, str]) -> dict[str, str]:
        request = Request(
            f"{self.api_url}/api/auth/refresh/",
            data=json.dumps({"refresh": tokens["refresh"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                refreshed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            exc.close()
            raise CameraAPISyncError("Could not refresh the agent login. Run agent/main.py --login again.") from exc
        except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            raise CameraAPISyncError("Could not refresh the agent login. Run agent/main.py --login again.") from exc
        if not refreshed.get("access"):
            raise CameraAPISyncError("Refreshed login did not include an access token. Run --login again.")
        tokens["access"] = refreshed["access"]
        self._save_tokens(tokens, expected_refresh=tokens["refresh"])
        return tokens

    def _send(self, payload: dict[str, Any]) -> None:
        tokens = self._read_tokens()
        try:
            self._post("/api/activity-events/ingest/", payload, tokens["access"])
        except CameraAPISyncError as exc:
            if getattr(exc, "status", None) != 401:
                raise
            tokens = self._refresh(tokens)
            self._post("/api/activity-events/ingest/", payload, tokens["access"])

    def log(self, state: str, duration_seconds: float, timestamp: datetime | None = None) -> None:
        """Persist a segment; background upload never blocks the frame loop on HTTP."""
        if duration_seconds <= 0:
            return
        end = timestamp or datetime.now().astimezone()
        start = end - timedelta(seconds=duration_seconds)
        device_id = self._device_id()
        queue = []
        for beginning, finish in split_interval(start, end):
            payload: dict[str, Any] = {
                "timestamp": finish.isoformat(),
                "state": state,
                "duration_seconds": (finish - beginning).total_seconds(),
            }
            if device_id:
                payload["device_id"] = device_id
            queue.append(payload)
        try:
            self._worker.append_many(queue)
        except OSError as exc:
            raise CameraAPISyncError(f"Could not persist camera queue: {exc}") from exc
        self._worker.request_flush()
