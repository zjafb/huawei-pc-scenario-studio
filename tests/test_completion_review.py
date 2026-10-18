"""Synthetic regression checks for final integration; never real marketing output."""
import copy
import hashlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import images, pipeline, ui
from app.pipeline import Report
import test_pipeline as fixture_module

MOMENTS_OK = fixture_module.MOMENTS_OK
FakeModel = fixture_module.FakeModel


class CompletionReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.PipelineTests("test_test_mode_never_qualified")
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_invisible_metadata_is_not_a_visible_fact_citation(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["article"]["body"][0]["text"] = out["article"]["body"][0]["text"].replace("[F1]", "")
        rep = self.fixture.run_task(out, mode="cache")
        self.assertIn(rep.status, ("failed", "blocked"))
        self.assertFalse(next(c for c in rep.checks if c["name"] == "事实依据")["ok"])

    def test_whitespace_citation_normalized_before_qualifier_checks(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["article"]["body"][0]["text"] = out["article"]["body"][0]["text"].replace("[F1]", "[ F1 ]")
        rep = self.fixture.run_task(out, mode="cache")
        self.assertEqual("qualified", rep.status)
        self.assertIn("[F1]", rep.article["body"][0]["text"])

    def test_spoofed_image_source_rejected(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["images"][0]["source"] = "SYNTHETIC-WRONG-SOURCE"
        rep = self.fixture.run_task(out, mode="cache")
        self.assertEqual("failed", rep.status)

    def test_model_self_assessment_not_exported_as_authoritative_check(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["notes_for_review"] = ["SYNTHETIC-FALSE-SELF-APPROVAL"]
        rep = self.fixture.run_task(out, mode="cache")
        self.assertIn("SYNTHETIC-FALSE-SELF-APPROVAL", rep.run["model_notes"])
        self.assertNotIn("SYNTHETIC-FALSE-SELF-APPROVAL", pipeline.to_text(rep))

    def test_free_text_reaches_model_and_request_precheck(self):
        client = FakeModel(copy.deepcopy(MOMENTS_OK))
        with patch.object(client, "chat_json", wraps=client.chat_json) as call:
            rep = pipeline.run_task(product="D14", variant="标准版", os_name="Windows", audience="新生",
                scene="school", platform="moments", free_text="SYNTHETIC-补充：加国补立减", mode="cache", model_client=client)
        self.assertIn("SYNTHETIC-补充", call.call_args.args[0][1]["content"])
        self.assertTrue(rep.blocked_requests)

    def test_image_payload_is_same_verified_original(self):
        rep = self.fixture.run_task(copy.deepcopy(MOMENTS_OK), mode="cache")
        self.assertEqual(rep.images[0]["sha256"], hashlib.sha256(rep.image_payloads["I1"]).hexdigest())
        self.assertIn("文末", pipeline.to_text(rep))

    def test_number_without_local_visible_citation_is_blocked(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["article"]["lead"] = "SYNTHETIC-数字挪用：1.39 kg。"
        rep = self.fixture.run_task(out, mode="cache")
        self.assertEqual("blocked", rep.status)

    def test_strategy_cannot_claim_an_unknown_fact(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["strategy"]["selected_points"][0]["fact_ids"] = ["F99"]
        rep = self.fixture.run_task(out, mode="cache")
        self.assertEqual("failed", rep.status)
        self.assertFalse(next(c for c in rep.checks if c["name"] == "策略依据")["ok"])

    def test_combined_hashtags_are_only_normalized_as_formatting(self):
        out = copy.deepcopy(MOMENTS_OK)
        out["article"]["title"] = "SYNTHETIC-选购前先确认这几件事"
        out["article"]["body"] += [{"text": "合成场景：选购前请先核对使用需求，确认版本和系统，再到店亲手看看实物。" * 2, "fact_ids": []}] * 2
        out["article"]["tags"] = ["#合成话题甲 #合成话题乙 #合成话题丙 #合成话题丁"]
        rep = self.fixture.run_task(out, mode="cache", platform="小红书")
        self.assertEqual(4, len(rep.article["tags"]))
        self.assertEqual("restricted", rep.status, rep.checks)

    def test_cache_repair_has_one_real_second_attempt_and_keeps_first_failure(self):
        bad = copy.deepcopy(MOMENTS_OK)
        bad["article"]["tags"] = ["#wrong-for-moments"]
        class SequenceModel:
            model = "SYNTHETIC-SEQUENCE"
            def __init__(self):
                self.stats = {"model_requests": 0}
            def chat_json(self, messages, **kwargs):
                self.stats["model_requests"] += 1
                return copy.deepcopy(bad if self.stats["model_requests"] == 1 else MOMENTS_OK)
        model = SequenceModel()
        rep = pipeline.run_task(product="D14", variant="标准版", os_name="Windows", scene="school",
                                platform="moments", mode="cache", model_client=model)
        self.assertEqual("qualified", rep.status)
        self.assertEqual(2, rep.run["model_stats"]["model_requests"])
        self.assertEqual(2, rep.run["repair"]["attempts"])
        self.assertEqual("failed", rep.run["repair"]["first_status"])
        self.assertIn("程序核验反馈", rep.run["prompt_messages"][1]["content"])
        self.assertEqual(4, rep.run["source_stats"]["cache_hits"])

    def test_repeated_bad_output_stops_after_two_attempts(self):
        bad = copy.deepcopy(MOMENTS_OK)
        bad["article"]["tags"] = ["#wrong-for-moments"]
        model = FakeModel(bad)
        rep = pipeline.run_task(product="D14", variant="标准版", os_name="Windows", scene="school",
                                platform="moments", mode="cache", model_client=model)
        self.assertEqual("failed", rep.status)
        self.assertEqual(2, model.calls)


class CompletionUIReviewTests(unittest.TestCase):
    def test_context_reset_removes_article_image_export_and_previous_draft(self):
        result = ui.reset_ui()
        self.assertEqual("", result[3])
        self.assertEqual("", result[5])
        self.assertEqual([], result[6])
        self.assertIsNone(result[7])
        self.assertIsNone(result[8])

    def invoke(self, report, product="D14", previous=None, extra=""):
        with patch("app.ui.pl.run_task", return_value=report) as run, patch("app.ui.save_run", return_value=Path("SYNTHETIC-record.json")):
            result = ui.run_ui(product, "新生", "school", "moments", "", "标准版", "Windows", extra,
                               "cache", previous)
        return result, run.call_args.kwargs

    def test_current_gradio_build_constructs_gallery_and_state(self):
        demo = ui.build()
        types = {component["type"] for component in demo.config["components"]}
        self.assertTrue({"gallery", "state", "file"}.issubset(types))

    def test_decodable_original_and_export_are_returned(self):
        stream = io.BytesIO()
        Image.new("RGB", (8, 4), "blue").save(stream, format="PNG")
        report = Report(status="qualified", images=[{"id": "SYNTHETIC-I", "name": "synthetic"}],
                        image_payloads={"SYNTHETIC-I": stream.getvalue()})
        result, _ = self.invoke(report)
        self.assertEqual((8, 4), result[6][0][0].size)
        self.assertEqual(result[5], Path(result[7]).read_text(encoding="utf-8-sig"))

    def test_invalid_image_downgrades_and_hides_draft(self):
        report = Report(status="qualified", article={"lead": "SYNTHETIC-HIDDEN"},
                        images=[{"id": "SYNTHETIC-I", "name": "test"}], image_payloads={"SYNTHETIC-I": b"broken"})
        result, _ = self.invoke(report)
        self.assertEqual("failed", report.status)
        self.assertEqual([], result[6])
        self.assertNotIn("SYNTHETIC-HIDDEN", result[3])

    def test_previous_article_only_used_when_identity_matches(self):
        previous = {"key": ["D14", "标准版", "Windows", "cache", "awareness", "moments", "新生", "school"], "article": {"lead": "SYNTHETIC-PREVIOUS"}}
        _, same = self.invoke(Report(status="need_info"), previous=previous, extra="改写")
        self.assertEqual(previous["article"], same["previous_article"])
        result, changed = self.invoke(Report(status="need_info"), product="D16", previous=previous, extra="改写")
        self.assertIsNone(changed["previous_article"])
        self.assertIsNone(result[8])

    def test_switching_marketing_goal_cannot_reuse_previous_draft(self):
        previous={"key":["D14","标准版","Windows","cache","store","moments","新生","school"],"article":{"lead":"SYNTHETIC-PREVIOUS"}}
        _,called=self.invoke(Report(status="need_info"),previous=previous,extra="改写")
        self.assertIsNone(called['previous_article'])
        self.assertEqual('awareness',called['marketing_goal'])


if __name__ == "__main__":
    unittest.main()
