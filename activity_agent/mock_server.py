"""Туршилтын backend: Agent -> API -> DB урсгалыг шалгах (Өдөр 3-5).

    python mock_server.py --port 8000 --db data/activity.db

Endpoints:
    GET  /health
    POST /api/v1/activity                         agent-ийн 60 сек batch
    POST /api/v1/camera                           camera module-ийн event {employee_id, timestamp, event}
    GET  /api/v1/summary?employee_id=..&date=..   activity summary + camera event-ууд (нэг employee/date)
"""

import argparse
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from contract import parse_iso, validate_batch
from summary import summarize

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE (employee_id, device_id, period_start)
);
CREATE TABLE IF NOT EXISTS camera_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    event TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path, tz_offset_hours):
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.tz = timezone(timedelta(hours=tz_offset_hours))

    def add_batch(self, batch):
        """Retry-аар ирсэн давхар batch-ийг алгасна (idempotent). True: шинээр нэмэгдсэн."""
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO activity_batches "
                "(employee_id, device_id, period_start, period_end, payload, received_at) VALUES (?,?,?,?,?,?)",
                (batch["employee_id"], batch["device_id"], batch["period_start"], batch["period_end"],
                 json.dumps(batch), datetime.now(timezone.utc).isoformat()),
            )
            return cur.rowcount == 1

    def add_camera_event(self, event):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO camera_events (employee_id, timestamp, event) VALUES (?,?,?)",
                              (event["employee_id"], event["timestamp"], event["event"]))

    def _utc_range(self, date):
        """Орон нутгийн огноог (жишээ нь UTC+8) UTC цагийн муж руу хөрвүүлнэ."""
        local_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=self.tz)
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        start = local_start.astimezone(timezone.utc)
        return start.strftime(fmt), (start + timedelta(days=1)).strftime(fmt)

    def daily(self, employee_id, date):
        start, end = self._utc_range(date)
        with self.lock:
            batches = [json.loads(row[0]) for row in self.conn.execute(
                "SELECT payload FROM activity_batches WHERE employee_id=? AND period_start>=? AND period_start<? "
                "ORDER BY period_start", (employee_id, start, end))]
            camera = [{"timestamp": t, "event": e} for t, e in self.conn.execute(
                "SELECT timestamp, event FROM camera_events WHERE employee_id=? AND timestamp>=? AND timestamp<? "
                "ORDER BY timestamp", (employee_id, start, end))]
        return {"employee_id": employee_id, "date": date,
                "activity": summarize(batches), "camera_events": camera}


def make_handler(store, api_token):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length) or b"null")

        def _authorized(self):
            return self.headers.get("Authorization") == f"Bearer {api_token}"

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self._json(200, {"status": "ok"})
            if url.path == "/api/v1/summary":
                if not self._authorized():
                    return self._json(401, {"error": "unauthorized"})
                q = parse_qs(url.query)
                try:
                    return self._json(200, store.daily(q["employee_id"][0], q["date"][0]))
                except (KeyError, ValueError):
                    return self._json(400, {"error": "employee_id and date=YYYY-MM-DD required"})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if not self._authorized():
                return self._json(401, {"error": "unauthorized"})
            try:
                data = self._read_json()
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})

            if path == "/api/v1/activity":
                errors = validate_batch(data)
                if errors:
                    return self._json(422, {"errors": errors})
                created = store.add_batch(data)
                return self._json(201 if created else 200, {"stored": created})

            if path == "/api/v1/camera":
                try:
                    parse_iso(data["timestamp"])
                    store.add_camera_event(data)
                except (KeyError, TypeError, ValueError):
                    return self._json(422, {"error": "need employee_id, event, timestamp (UTC ISO)"})
                return self._json(201, {"stored": True})

            self._json(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            print(f"[api] {self.address_string()} {fmt % args}")

    return Handler


def make_server(host, port, db_path, api_token, tz_offset_hours=8):
    store = Store(db_path, tz_offset_hours)
    return ThreadingHTTPServer((host, port), make_handler(store, api_token))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "activity.db"))
    parser.add_argument("--token", default="dev-token")
    parser.add_argument("--tz-offset", type=int, default=8, help="Орон нутгийн цагийн бүс (Монгол: 8)")
    args = parser.parse_args()

    server = make_server(args.host, args.port, args.db, args.token, args.tz_offset)
    print(f"Mock API: http://{args.host}:{args.port}  (db: {args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
