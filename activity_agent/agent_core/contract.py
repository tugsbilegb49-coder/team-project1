"""Activity JSON contract (Өдөр 2).

Agent 60 секунд тутам НЭГ batch илгээнэ. Batch-д зөвхөн тоо, хугацаа байна:
товчлуурын текст, mouse координат, цонхны гарчиг, clipboard БАЙХГҮЙ.

Жишээ:
{
  "schema_version": "1.0",
  "agent_version": "0.1.0",
  "employee_id": "emp-001",
  "device_id": "3f9a...",
  "period_start": "2026-11-05T02:00:00Z",
  "period_end": "2026-11-05T02:01:00Z",
  "active_seconds": 42,
  "idle_seconds": 18,
  "keyboard_events": 120,
  "mouse_events": 15,
  "apps": [{"name": "chrome.exe", "seconds": 30}, {"name": "code.exe", "seconds": 12}]
}
"""

from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"
AGENT_VERSION = "0.1.0"

REQUIRED_FIELDS = {
    "schema_version": str,
    "agent_version": str,
    "employee_id": str,
    "device_id": str,
    "period_start": str,
    "period_end": str,
    "active_seconds": int,
    "idle_seconds": int,
    "keyboard_events": int,
    "mouse_events": int,
    "apps": list,
}

# Нууцлалын дүрэм: эдгээр түлхүүр batch-д хэзээ ч орох ёсгүй.
FORBIDDEN_FIELDS = {"keys", "text", "keystrokes", "password", "clipboard",
                    "x", "y", "coordinates", "window_title", "file_content"}


def utc_iso(ts):
    """Unix timestamp -> '2026-11-05T02:00:00Z' (camera module-тэй ижил UTC формат)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def build_batch(employee_id, device_id, period_start, period_end, stats):
    apps = sorted(stats["apps"].items(), key=lambda kv: kv[1], reverse=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_version": AGENT_VERSION,
        "employee_id": employee_id,
        "device_id": device_id,
        "period_start": utc_iso(period_start),
        "period_end": utc_iso(period_end),
        "active_seconds": int(round(stats["active_seconds"])),
        "idle_seconds": int(round(stats["idle_seconds"])),
        "keyboard_events": stats["keyboard_events"],
        "mouse_events": stats["mouse_events"],
        "apps": [{"name": name, "seconds": int(round(sec))} for name, sec in apps if sec >= 0.5],
    }


def validate_batch(batch):
    """Алдааны жагсаалт буцаана; хоосон бол batch зөв."""
    if not isinstance(batch, dict):
        return ["batch must be a JSON object"]

    errors = []
    for field, expected in REQUIRED_FIELDS.items():
        if field not in batch:
            errors.append(f"missing field: {field}")
        elif not isinstance(batch[field], expected) or isinstance(batch[field], bool):
            errors.append(f"{field} must be {expected.__name__}")

    for field in FORBIDDEN_FIELDS & batch.keys():
        errors.append(f"forbidden field: {field}")
    if errors:
        return errors

    if batch["schema_version"] != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {batch['schema_version']}")

    try:
        start, end = parse_iso(batch["period_start"]), parse_iso(batch["period_end"])
        if end <= start:
            errors.append("period_end must be after period_start")
        elif batch["active_seconds"] + batch["idle_seconds"] > (end - start).total_seconds() + 2:
            errors.append("active_seconds + idle_seconds exceeds period length")
    except ValueError:
        errors.append("period_start/period_end must be ISO-8601 UTC like 2026-11-05T02:00:00Z")

    for name in ("active_seconds", "idle_seconds", "keyboard_events", "mouse_events"):
        if batch[name] < 0:
            errors.append(f"{name} must be >= 0")

    for app in batch["apps"]:
        if (not isinstance(app, dict) or set(app) != {"name", "seconds"}
                or not isinstance(app["name"], str) or not isinstance(app["seconds"], int)):
            errors.append("apps items must be {name: str, seconds: int}")
            break

    return errors
