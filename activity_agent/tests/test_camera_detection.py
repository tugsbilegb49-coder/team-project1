import unittest

from agent_core.contract import parse_iso
from camera_ai.person_detection import utc_timestamp


class CameraTimestampTest(unittest.TestCase):
    def test_timestamp_matches_api_utc_format(self):
        timestamp = utc_timestamp()
        self.assertRegex(timestamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIsNotNone(parse_iso(timestamp))


if __name__ == "__main__":
    unittest.main()