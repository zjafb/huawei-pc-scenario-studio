"""Evidence checks on clearly synthetic facts and signatures."""
import unittest

from app.evidence import approval_issue, quote_issue, scope_covers
from app.whitelist import Task


class EvidenceReviewTests(unittest.TestCase):
    def test_composite_value_needs_all_quoted_parts(self):
        text = "size: 14 inches\ntype: IPS\nratio: 16:10"
        fact = {"value": "14 inches、IPS、16:10", "quote": "14 inches"}
        self.assertTrue(quote_issue(fact, text))
        fact["quotes"] = ["14 inches", "IPS", "16:10"]
        self.assertEqual("", quote_issue(fact, text))

    def test_quote_absent_from_source_is_invalid(self):
        self.assertTrue(quote_issue({"value": "1 kg", "quote": "1 kg"}, "2 kg"))

    def test_qualifier_requires_original_support(self):
        fact = {"value": "100% sRGB（典型值）", "quote": "100% sRGB", "must_keep": ["典型值"]}
        self.assertTrue(quote_issue(fact, "100% sRGB"))
        self.assertEqual("", quote_issue(fact, "100% sRGB\n色域为典型值"))

    def test_unknown_scope_cannot_be_inferred_from_two_other_dimensions(self):
        task = Task("D 14", variant="标准版", os="Windows")
        scope = {"model": "D 14", "year": 2024, "variants": ["标准版"], "os": []}
        self.assertFalse(scope_covers(scope, task)[0])

    def test_only_calendar_date_format_is_accepted(self):
        approval = {"status": "approved", "checked_by": "SYNTHETIC-A", "reviewed_by": "SYNTHETIC-B", "date": "2026-10-18"}
        self.assertEqual("", approval_issue(approval))
        for value in ("20261018", "2026-W42-7", "2026-02-30", "x", "", None):
            with self.subTest(value=value):
                self.assertTrue(approval_issue({**approval, "date": value}))

    def test_ai_and_placeholder_are_not_human_signatures(self):
        approval = {"status": "approved", "checked_by": "SYNTHETIC-A", "reviewed_by": "SYNTHETIC-B", "date": "2026-10-18"}
        for name in ("Codex", "Claude", "待签字", "待确认", "___", "   "):
            self.assertTrue(approval_issue({**approval, "checked_by": name}))


if __name__ == "__main__":
    unittest.main()
