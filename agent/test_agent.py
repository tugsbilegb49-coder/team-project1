import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import (
    application_for_idle_state,
    category_for,
    display_name_for_windows_process,
    is_paused,
    segment_payload,
    set_paused,
)


class AgentHelpersTests(unittest.TestCase):
    def test_configured_application_is_work(self):
        self.assertEqual(category_for("Visual Studio Code", ["Visual Studio Code"]), "WORK")

    def test_browser_is_not_assumed_to_be_work(self):
        self.assertEqual(category_for("Safari", []), "BROWSER")

    def test_windows_process_name_does_not_use_a_window_title(self):
        self.assertEqual(display_name_for_windows_process("WINWORD"), "Microsoft Word")
        self.assertEqual(display_name_for_windows_process("unknown_process"), "unknown_process")

    def test_segment_keeps_application_and_duration(self):
        from datetime import datetime, timedelta, timezone

        started_at = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
        payload = segment_payload("Visual Studio Code", "WORK", started_at, started_at + timedelta(seconds=30))
        self.assertEqual(payload["application"], "Visual Studio Code")
        self.assertEqual(payload["duration_seconds"], 30)

    def test_pause_control_is_local_and_reversible(self):
        with TemporaryDirectory() as directory:
            control_file = Path(directory) / "control.json"
            self.assertFalse(is_paused(control_file))
            set_paused(True, control_file)
            self.assertTrue(is_paused(control_file))
            set_paused(False, control_file)
            self.assertFalse(is_paused(control_file))

    def test_idle_threshold_hides_foreground_application_without_reading_input(self):
        self.assertEqual(application_for_idle_state("Visual Studio Code", 301, 300), "Idle")
        self.assertEqual(application_for_idle_state("Visual Studio Code", 30, 300), "Visual Studio Code")

