"""Synthetic orchestration checks. No network and no real approvals."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.images import ImageResult
from app.pipeline import _check_image_refs, run_task
from app.whitelist import FactPool


class SyntheticClient:
    model = "SYNTHETIC-NO-NETWORK"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def chat_json(self, *args, **kwargs):
        self.calls += 1
        return self.response


class PipelineReviewTests(unittest.TestCase):
    def test_image_selected_but_omitted_from_output_is_not_complete(self):
        ok, _ = _check_image_refs([{"id": "SYNTHETIC-IMAGE"}], [])
        self.assertFalse(ok, "An empty output-image list must not pass as a complete illustrated article.")

    def test_repeated_model_image_cannot_count_twice(self):
        row = {"image_id": "SYNTHETIC-IMAGE", "source": "fixture", "caption": "fixture", "position": "fixture"}
        ok, _ = _check_image_refs([{"id": "SYNTHETIC-IMAGE"}], [row, row])
        self.assertFalse(ok)

    def test_live_or_unknown_mode_cannot_generate_using_cache_only(self):
        fact = {"id": "TEST-01", "category": "便携", "value": "约 1 kg", "quote": "约 1 kg", "usage": "body"}
        fake_pool = FactPool(allowed=[fact], mode="cache")
        for mode in ("live", "unsupported-mode"):
            with self.subTest(mode=mode):
                client = SyntheticClient({})
                with patch("app.pipeline.make_live_reader", return_value=SimpleNamespace(mode="cache", failure=None)), patch("app.pipeline.build_fact_pool", return_value=fake_pool), patch(
                        "app.pipeline.select_images", return_value=ImageResult(needed_min=1, needed_max=3)):
                    report = run_task(product="D 14 2024", audience="大学新生", scene="school",
                                      platform="moments", variant="标准版", os_name="Windows",
                                      model_client=client, mode=mode)
                self.assertEqual("failed", report.status)
                self.assertEqual(0, client.calls, "A non-cache mode must not silently use cached sources.")

    def test_malformed_model_article_is_reported_instead_of_crashing(self):
        fact = {"id": "TEST-01", "category": "便携", "value": "约 1 kg", "quote": "约 1 kg", "usage": "body"}
        client = SyntheticClient({"article": "incorrect JSON type"})
        with patch("app.pipeline.build_fact_pool", return_value=FactPool(allowed=[fact])), patch(
                "app.pipeline.select_images", return_value=ImageResult(needed_min=1, needed_max=3)):
            report = run_task(product="D 14 2024", audience="大学新生", scene="school", platform="moments",
                              variant="标准版", os_name="Windows", model_client=client, mode="test")
        self.assertEqual("failed", report.status)


if __name__ == "__main__":
    unittest.main()
