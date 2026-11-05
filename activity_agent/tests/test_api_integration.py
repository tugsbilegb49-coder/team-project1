"""Өдөр 3-6: Agent -> API -> DB, camera холбоо, network алдаа ба restart."""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract import build_batch
from mock_server import make_server
from sender import BatchSender

TOKEN = "test-token"
STATS = {"active_seconds": 50, "idle_seconds": 10, "keyboard_events": 5, "mouse_events": 2,
         "apps": {"code.exe": 50}}
# 2026-11-05 10:00 Улаанбаатар (UTC+8) = 02:00 UTC
START = 1_793_844_000


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def batch_at(offset):
    return build_batch("emp-001", "dev1", START + offset, START + offset + 60, STATS)


class ApiIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.spool = os.path.join(self.tmp, "spool.jsonl")
        self.server = None

    def tearDown(self):
        self.stop_server()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start_server(self):
        self.server = make_server("127.0.0.1", self.port, os.path.join(self.tmp, "a.db"), TOKEN)
        self.server.RequestHandlerClass.log_message = lambda *a: None
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def sender(self, token=TOKEN):
        return BatchSender(self.url + "/api/v1/activity", token, self.spool, timeout=2)

    def request(self, path, data=None):
        req = urllib.request.Request(self.url + path, method="POST" if data else "GET",
                                     data=json.dumps(data).encode() if data else None,
                                     headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read())

    def test_agent_to_db_and_summary(self):
        self.start_server()
        sender = self.sender()
        for i in range(3):
            self.assertEqual(sender.send(batch_at(i * 60)), (1, 0))
        daily = self.request("/api/v1/summary?employee_id=emp-001&date=2026-11-05")
        self.assertEqual(daily["activity"]["batches"], 3)
        self.assertEqual(daily["activity"]["active_seconds"], 150)

    def test_camera_linked_by_employee_and_date(self):
        self.start_server()
        self.sender().send(batch_at(0))
        self.request("/api/v1/camera", {"employee_id": "emp-001", "timestamp": "2026-11-05T02:00:30Z",
                                        "event": "face_present"})
        self.request("/api/v1/camera", {"employee_id": "emp-001", "timestamp": "2026-11-06T02:00:30Z",
                                        "event": "other_day"})
        daily = self.request("/api/v1/summary?employee_id=emp-001&date=2026-11-05")
        self.assertEqual(daily["camera_events"], [{"timestamp": "2026-11-05T02:00:30Z", "event": "face_present"}])
        self.assertEqual(daily["activity"]["batches"], 1)

    def test_network_down_then_recovers(self):
        sender = self.sender()
        self.assertEqual(sender.send(batch_at(0)), (0, 1))   # сервер унтарсан
        self.assertEqual(sender.send(batch_at(60)), (0, 2))
        self.start_server()
        restarted = self.sender()                             # agent restart: шинэ объект, ижил spool
        self.assertEqual(restarted.send(batch_at(120)), (3, 0))
        daily = self.request("/api/v1/summary?employee_id=emp-001&date=2026-11-05")
        self.assertEqual(daily["activity"]["batches"], 3)

    def test_duplicate_retry_is_idempotent(self):
        self.start_server()
        sender = self.sender()
        sender.send(batch_at(0))
        sender.send(batch_at(0))
        daily = self.request("/api/v1/summary?employee_id=emp-001&date=2026-11-05")
        self.assertEqual(daily["activity"]["batches"], 1)

    def test_rejected_batch_not_retried_forever(self):
        self.start_server()
        self.assertEqual(self.sender(token="wrong").send(batch_at(0)), (1, 0))
        bad = batch_at(60)
        bad["password"] = "x"
        self.assertEqual(self.sender().send(bad), (1, 0))

    def test_corrupt_spool_line_skipped(self):
        with open(self.spool, "w") as f:
            f.write("{not json\n")
        self.start_server()
        self.assertEqual(self.sender().send(batch_at(0)), (1, 0))


if __name__ == "__main__":
    unittest.main()
