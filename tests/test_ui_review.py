"""Presentation checks use synthetic reports, no model/network calls."""
import unittest

from app.pipeline import Report, to_text
from app.ui import _section


class UIReviewTests(unittest.TestCase):
    def test_blocked_and_failed_article_never_shown_as_publishable_body(self):
        for status in ("blocked", "failed"):
            with self.subTest(status=status):
                report = Report(status=status, mode="live", message="Synthetic validation failure",
                                article={"lead": "UNSAFE-SYNTHETIC-SENTINEL", "body": [], "cta": ""})
                self.assertNotIn("UNSAFE-SYNTHETIC-SENTINEL", to_text(report))
                self.assertNotIn("UNSAFE-SYNTHETIC-SENTINEL", _section(report, 3))

    def test_safe_restricted_draft_may_be_presented_with_its_status(self):
        report = Report(status="restricted", mode="live", image_shortage="Synthetic image shortage",
                        article={"lead": "SAFE-SYNTHETIC-SENTINEL", "body": [], "cta": ""})
        self.assertIn("SAFE-SYNTHETIC-SENTINEL", _section(report, 3))
        self.assertIn("Synthetic image shortage", to_text(report))


if __name__ == "__main__":
    unittest.main()
