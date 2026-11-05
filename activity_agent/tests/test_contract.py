import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract import build_batch, validate_batch
from summary import summarize

STATS = {"active_seconds": 40.4, "idle_seconds": 19.6, "keyboard_events": 10, "mouse_events": 3,
         "apps": {"chrome.exe": 25.2, "code.exe": 15.2, "tiny.exe": 0.1}}


def sample(start=1_762_300_000):
    return build_batch("emp-001", "dev1", start, start + 60, STATS)


class ContractTest(unittest.TestCase):
    def test_built_batch_is_valid(self):
        batch = sample()
        self.assertEqual(validate_batch(batch), [])
        self.assertEqual(batch["active_seconds"], 40)
        self.assertEqual(batch["apps"][0], {"name": "chrome.exe", "seconds": 25})
        self.assertEqual(len(batch["apps"]), 2)
        self.assertTrue(batch["period_start"].endswith("Z"))

    def test_missing_and_forbidden_fields(self):
        batch = sample()
        del batch["idle_seconds"]
        batch["keystrokes"] = "hello"
        errors = validate_batch(batch)
        self.assertIn("missing field: idle_seconds", errors)
        self.assertIn("forbidden field: keystrokes", errors)

    def test_time_more_than_period(self):
        batch = sample()
        batch["active_seconds"] = 500
        self.assertTrue(any("exceeds" in e for e in validate_batch(batch)))

    def test_bad_types(self):
        batch = sample()
        batch["mouse_events"] = "3"
        batch["apps"] = [{"name": "x"}]
        self.assertIn("mouse_events must be int", validate_batch(batch))

    def test_summary(self):
        result = summarize([sample(), sample(1_762_300_060)])
        self.assertEqual(result["active_seconds"], 80)
        self.assertEqual(result["idle_seconds"], 40)
        self.assertEqual(result["active_ratio"], round(80 / 120, 4))
        self.assertEqual(result["top_apps"][0]["name"], "chrome.exe")
        self.assertEqual(summarize([])["active_ratio"], 0.0)


if __name__ == "__main__":
    unittest.main()
