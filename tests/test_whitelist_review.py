"""Codex review: synthetic source, never team approvals or marketing results."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.whitelist import Task, build_fact_pool
from connectors import VerifiedCache


class WhitelistReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "synthetic.md"
        self.source.write_text("# Synthetic fixture\nWeight: approximately 1 kg.\n", encoding="utf-8")
        self.fact = {
            "id": "TEST-01", "source": "TEST", "attr": "weight", "category": "便携",
            "value": "approximately 1 kg", "quote": "approximately 1 kg", "usage": "body",
            "conclusion": "usable", "must_keep": ["approximately"], "caveat": "",
            "scope": {"model": "D 14", "year": 2024,
                      "variants": ["标准版", "SE 版"], "os": ["Windows", "Linux"]},
            "approval": {"status": "approved", "checked_by": "SYNTHETIC-CHECKER",
                         "reviewed_by": "SYNTHETIC-REVIEWER", "date": "2026-10-18"},
        }
        self.task = Task("D 14", variant="标准版", os="Windows")

    def pool(self, fact=None, task=None):
        raw = {"_来源": {"TEST": {"file": "synthetic.md", "title": "Synthetic fixture",
                "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest()}},
               "facts": [copy.deepcopy(fact if fact is not None else self.fact)]}
        with patch("app.whitelist.load_raw", return_value=raw):
            return build_fact_pool(task or self.task, VerifiedCache(self.directory.name))

    def test_valid_explicit_scope_and_real_quote_allowed(self):
        self.assertEqual(["TEST-01"], [f["id"] for f in self.pool().allowed])

    def test_missing_variant_scope_not_wildcard(self):
        del self.fact["scope"]["variants"]
        self.assertFalse(self.pool().allowed, "Unknown variant coverage must not become universal.")

    def test_missing_os_scope_not_wildcard(self):
        del self.fact["scope"]["os"]
        self.assertFalse(self.pool().allowed, "Unknown OS coverage must not become universal.")

    def test_two_os_values_do_not_cover_third_os(self):
        task = Task("D 14", variant="标准版", os="Other OS")
        self.assertFalse(self.pool(task=task).allowed)

    def test_same_checker_and_reviewer_rejected(self):
        self.fact["approval"]["reviewed_by"] = self.fact["approval"]["checked_by"]
        self.assertFalse(self.pool().allowed, "Independent review needs distinct people.")

    def test_approval_without_date_rejected(self):
        self.fact["approval"]["date"] = ""
        self.assertFalse(self.pool().allowed)

    def test_placeholder_signatures_rejected(self):
        self.fact["approval"].update(checked_by="待签字", reviewed_by="待确认")
        self.assertFalse(self.pool().allowed)

    def test_quote_must_exist_in_verified_source(self):
        self.fact["quote"] = "a fabricated value absent from source"
        self.assertFalse(self.pool().allowed, "Matching whole-file hash alone does not validate quote.")

    def test_different_model_excluded_without_mutating_approval(self):
        self.assertFalse(self.pool(task=Task("D 16", variant="标准版", os="Windows")).allowed)
        self.assertEqual("approved", self.fact["approval"]["status"])
        self.assertTrue(self.pool().allowed)

    def test_pending_never_allowed(self):
        self.fact["approval"]["status"] = "pending"
        self.assertFalse(self.pool().allowed)

    def test_changing_source_manifest_does_not_reapprove_changed_source(self):
        self.fact["approval"]["source_sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.source.write_text(self.source.read_text() + "changed source version\n", encoding="utf-8")
        self.assertFalse(self.pool().allowed)


if __name__ == "__main__":
    unittest.main()
