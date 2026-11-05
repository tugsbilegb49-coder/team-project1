"""W metric-д зориулсан active/idle/app summary (Өдөр 5)."""

from collections import defaultdict


def summarize(batches, top_apps=10):
    """Нэг ажилтны нэг өдрийн batch-уудаас score service-д өгөх summary гаргана."""
    active = sum(b["active_seconds"] for b in batches)
    idle = sum(b["idle_seconds"] for b in batches)
    apps = defaultdict(int)
    for b in batches:
        for app in b["apps"]:
            apps[app["name"]] += app["seconds"]

    tracked = active + idle
    ranked = sorted(apps.items(), key=lambda kv: kv[1], reverse=True)[:top_apps]
    return {
        "batches": len(batches),
        "first_seen": min((b["period_start"] for b in batches), default=None),
        "last_seen": max((b["period_end"] for b in batches), default=None),
        "active_seconds": active,
        "idle_seconds": idle,
        "tracked_seconds": tracked,
        "active_ratio": round(active / tracked, 4) if tracked else 0.0,
        "keyboard_events": sum(b["keyboard_events"] for b in batches),
        "mouse_events": sum(b["mouse_events"] for b in batches),
        "top_apps": [
            {"name": name, "seconds": sec, "share": round(sec / active, 4) if active else 0.0}
            for name, sec in ranked
        ],
    }
