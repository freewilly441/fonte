import json
import tempfile
import unittest
from pathlib import Path

from analytics import AnalyticsTracker


class AnalyticsTests(unittest.TestCase):
    def test_redacts_sensitive_payload(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "analytics.log"
            tracker = AnalyticsTracker(log_path)
            tracker.track("api_error", token="abc123", password="x", detail="ok")

            row = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(row["token"], "[redacted]")
            self.assertEqual(row["password"], "[redacted]")
            self.assertEqual(row["detail"], "ok")


if __name__ == "__main__":
    unittest.main()
