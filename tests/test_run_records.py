"""Synthetic history tests with temporary directories and synthetic keys."""
import json
import tempfile
import unittest

from app.pipeline import Report
from run_records import save_run


class RunRecordTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_live_failure_preserves_mode_error_and_counts(self):
        report = Report(mode="live", status="failed", message="Synthetic quota",
                        run={"source_stats": {"api_requests": 1, "cache_hits": 0}})
        path = save_run(report, directory=self.folder.name, secrets=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("live", path.parent.name)
        self.assertFalse(data["synthetic_test"])
        self.assertEqual(0, data["report"]["run"]["source_stats"]["cache_hits"])
        self.assertEqual("failed", data["report"]["status"])

    def test_test_history_separate_and_never_overwrites(self):
        report = Report(mode="test", status="restricted")
        a = save_run(report, directory=self.folder.name, secrets=[])
        b = save_run(report, directory=self.folder.name, secrets=[])
        self.assertNotEqual(a, b)
        self.assertEqual("test", a.parent.name)
        self.assertTrue(json.loads(a.read_text())["synthetic_test"])

    def test_secret_redacted_without_truncating_long_text(self):
        secret = "SYNTHETIC-RECORD-SECRET-12345"
        report = Report(mode="test", message="x" * 3000 + secret)
        path = save_run(report, directory=self.folder.name, secrets=[secret])
        encoded = path.read_text(encoding="utf-8")
        self.assertNotIn(secret, encoded)
        self.assertIn("[REDACTED]", encoded)
        self.assertIn("x" * 3000, encoded)

    def test_cache_mode_saved_separately_from_live(self):
        path = save_run(Report(mode="cache"), directory=self.folder.name, secrets=[])
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("cache", path.parent.name)
        self.assertEqual("cache", data["report"]["mode"])
        self.assertFalse(data["synthetic_test"])


if __name__ == "__main__":
    unittest.main()
