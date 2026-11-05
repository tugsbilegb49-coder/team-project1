"""Optional Django API synchronisation for single-user camera sessions.

The webcam monitor continues to write its local CSV log even when the API is
offline. This uploader reuses the refresh token saved by agent/main.py and
never stores a password.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CameraAPISyncError(RuntimeError):
    """The local camera monitor can continue safely after a sync error."""


class CameraEventUploader:
    def __init__(self, api_url: str, token_file: str, device_config_file: str = "agent/config.json", queue_file: str = "data/.pending_camera_events.json"):
        self.api_url = api_url.rstrip("/")
        self.token_file = Path(token_file)
        self.device_config_file = Path(device_config_file)
        self.queue_file = Path(queue_file)

    def _device_id(self) -> str | None:
        try:
            return json.loads(self.device_config_file.read_text(encoding="utf-8")).get("device_id")
        except (OSError, json.JSONDecodeError, AttributeError):
            return None

    def _read_queue(self) -> list[dict[str, Any]]:
        if not self.queue_file.is_file():
            return []
        try:
            queue = json.loads(self.queue_file.read_text(encoding="utf-8"))
            return queue if isinstance(queue, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _write_queue(self, queue: list[dict[str, Any]]) -> None:
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.queue_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(queue), encoding="utf-8")
        temporary.replace(self.queue_file)

    def _read_tokens(self) -> dict[str, str]:
        if not self.token_file.is_file():
            raise CameraAPISyncError(
                f"Agent token not found at {self.token_file}. "
                "First run: python3 agent/main.py --login"
            )
        try:
            tokens = json.loads(self.token_file.read_text(encoding="utf-8"))
            if not tokens.get("access") or not tokens.get("refresh"):
                raise ValueError("missing token")
            return tokens
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CameraAPISyncError("Saved agent login is invalid. Run agent/main.py --login again.") from exc

    def _save_tokens(self, tokens: dict[str, str]) -> None:
        temporary = self.token_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(tokens), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.token_file)
        os.chmod(self.token_file, 0o600)

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
            error.status = exc.code
            raise error from exc
        except (URLError, TimeoutError) as exc:
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
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise CameraAPISyncError("Could not refresh the agent login. Run agent/main.py --login again.") from exc
        if not refreshed.get("access"):
            raise CameraAPISyncError("Refreshed login did not include an access token. Run --login again.")
        tokens["access"] = refreshed["access"]
        self._save_tokens(tokens)
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
        """Queue then send a completed camera segment for the authenticated employee."""
        payload: dict[str, Any] = {
            "timestamp": (timestamp or datetime.now().astimezone()).isoformat(),
            "state": state,
            "duration_seconds": round(duration_seconds, 1),
        }
        device_id = self._device_id()
        if device_id:
            payload["device_id"] = device_id
        queue = self._read_queue()
        queue.append(payload)
        self._write_queue(queue)
        while queue:
            self._send(queue[0])
            queue.pop(0)
            self._write_queue(queue)
