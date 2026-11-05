import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import ActivityCollector


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def run_seconds(collector, clock, seconds):
    for _ in range(seconds):
        clock.now += 1
        collector.tick()


class IdleTimerTest(unittest.TestCase):
    """Өдөр 6: 1/3/5 минутын idle test (fake clock тул шууд ажиллана)."""

    def make(self, threshold):
        clock = FakeClock()
        return ActivityCollector(threshold, clock=clock, app_resolver=lambda: "code.exe"), clock

    def check_idle(self, idle_minutes, threshold=60):
        collector, clock = self.make(threshold)
        collector.on_keyboard()
        run_seconds(collector, clock, idle_minutes * 60)
        stats = collector.flush()
        self.assertAlmostEqual(stats["active_seconds"], threshold - 1, delta=1)
        self.assertAlmostEqual(stats["idle_seconds"], idle_minutes * 60 - threshold + 1, delta=1)
        self.assertTrue(collector.is_idle())

    def test_idle_1_minute(self):
        self.check_idle(1, threshold=30)

    def test_idle_3_minutes(self):
        self.check_idle(3)

    def test_idle_5_minutes(self):
        self.check_idle(5)

    def test_input_returns_to_active(self):
        collector, clock = self.make(60)
        run_seconds(collector, clock, 120)
        self.assertTrue(collector.is_idle())
        collector.on_mouse()
        self.assertFalse(collector.is_idle())
        run_seconds(collector, clock, 10)
        self.assertGreater(collector.flush()["active_seconds"], 9)

    def test_counts_only_no_content(self):
        collector, clock = self.make(60)
        collector.on_keyboard("SECRET_KEY")
        collector._on_click(123, 456, "left", True)
        collector._on_click(123, 456, "left", False)
        collector.on_mouse_move(10, 20)
        stats = collector.flush()
        self.assertEqual(stats["keyboard_events"], 1)
        self.assertEqual(stats["mouse_events"], 1)
        self.assertNotIn("SECRET_KEY", repr(stats))
        self.assertNotIn("456", repr(stats))

    def test_app_seconds_only_when_active(self):
        collector, clock = self.make(60)
        collector.on_keyboard()
        run_seconds(collector, clock, 100)
        stats = collector.flush()
        self.assertAlmostEqual(stats["apps"]["code.exe"], stats["active_seconds"])

    def test_sleep_gap_ignored(self):
        collector, clock = self.make(60)
        clock.now += 3600  # laptop sleep
        collector.tick()
        stats = collector.flush()
        self.assertEqual(stats["active_seconds"] + stats["idle_seconds"], 0)

    def test_flush_resets(self):
        collector, clock = self.make(60)
        collector.on_keyboard()
        run_seconds(collector, clock, 5)
        collector.flush()
        stats = collector.flush()
        self.assertEqual(stats["active_seconds"], 0)
        self.assertEqual(stats["keyboard_events"], 0)


if __name__ == "__main__":
    unittest.main()
