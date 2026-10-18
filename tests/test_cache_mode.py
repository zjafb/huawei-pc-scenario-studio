"""Explicit cache-mode regression checks; no model or IMA requests."""
import unittest
from unittest.mock import patch

from app import pipeline, ui
from app.pipeline import Report
from connectors import VerifiedCache


class CacheModeTests(unittest.TestCase):
    def test_real_approved_source_cache_is_verified_without_ima(self):
        from app import whitelist
        if not whitelist.WHITELIST_FILE.exists():
            self.skipTest("Private real evidence is not distributed with public source.")
        class StopModel:
            model = "SYNTHETIC-NO-NETWORK"
            stats = {}
            def chat_json(self, *args, **kwargs):
                return {"status": "need_info", "questions": ["synthetic stop before generation"]}
        with patch("app.pipeline.make_live_reader", side_effect=AssertionError("IMA must not be used")):
            report = pipeline.run_task(product="D 14 2024", variant="标准版", os_name="Windows",
                                       scene="school", platform="moments", mode="cache", model_client=StopModel())
        self.assertEqual("cache", report.mode)
        self.assertIn("未验证远端当前最新", report.mode_note)
        self.assertIn("2026-10-18", report.mode_note)
        self.assertEqual(0, report.run["source_stats"]["api_requests"])
        self.assertGreater(report.run["source_stats"]["cache_hits"], 0)

    def test_cache_banner_and_export_do_not_claim_live(self):
        report = Report(mode="cache", status="need_info", mode_note="未验证远端当前最新")
        self.assertIn("模式：缓存", ui._banner(report))
        self.assertIn("模式：cache", pipeline.to_text(report))
        self.assertNotIn("模式：实时", ui._banner(report))

    def test_cache_has_explicit_reader_mode(self):
        self.assertEqual("cache", VerifiedCache.mode)

    def test_ui_default_passes_cache_and_saves_record(self):
        from pathlib import Path
        with patch("app.ui.pl.run_task", return_value=Report(mode="cache", status="need_info")) as run, patch(
                "app.ui.save_run", return_value=Path("synthetic-run.json")) as save:
            ui.run_ui("D14", "", "school", "moments", "", "", "", "")
        self.assertEqual("cache", run.call_args.kwargs["mode"])
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
