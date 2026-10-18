"""编排测试。使用合成白名单与假模型，全部为测试，结果不得当作真实运行成果。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import images as im           # noqa: E402
from app import pipeline as pl         # noqa: E402
from app import whitelist as wl        # noqa: E402
from connectors import ConnectorError, VerifiedCache  # noqa: E402

SRC = "D14 合成测试原文：约 1.39 kg。标准版与SE版不能混用。\n".encode("utf-8")
IMG = b"fake-png"
SRC_SHA = hashlib.sha256(SRC).hexdigest()
IMG_SHA = hashlib.sha256(IMG).hexdigest()
APPROVED = {"status": "approved", "checked_by": "SYNTHETIC-甲", "reviewed_by": "SYNTHETIC-乙", "date": "2026-10-18"}


def fact(fid, value, cat, must_keep=(), variants=("标准版", "SE 版"), usage="body"):
    return {"id": fid, "attr": "a", "category": cat, "value": value, "quote": value,
            "must_keep": list(must_keep), "caveat": "", "section": "测试章节",
            "scope": {"model": "D 14", "year": 2024, "variants": list(variants), "os": ["Windows", "Linux"]},
            "source": "S", "usage": usage, "approval": APPROVED}


class FakeModel:
    model = "fake-test-model"

    def __init__(self, out):
        self.out = out
        self.calls = 0

    def chat_json(self, messages, **kw):
        self.calls += 1
        if isinstance(self.out, Exception):
            raise self.out
        return self.out


MOMENTS_OK = {
    "scene_judgement": {"audience": "大学新生", "scene": "开学季", "problems": ["怕重"], "goal": "到店",
                        "purchase_stage": "比较中", "assumptions": []},
    "strategy": {"angle": "每天背着走的电脑",
                 "selected_points": [{"category": "便携", "fact_ids": ["F1"], "why": "携带"}],
                 "dropped_points": []},
    "article": {"title": "", "lead": "开学前，先想想每天要背的那台电脑。",
                "body": [{"text": "重量约 1.39 kg [F1]，实际依配置而异，背去教室更从容，选之前不妨亲手掂一掂。",
                          "fact_ids": ["F1"]}],
                "cta": "想亲手试试，欢迎来店看看。", "tags": []},
    "images": [{"image_id": "I1", "name": "外观", "source": "测试来源", "position": "文末", "caption": "整机外观"}],
    "notes_for_review": [],
}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "S.md").write_bytes(SRC)
        (self.dir / "i.png").write_bytes(IMG)
        self._wf, self._cd, self._if = wl.WHITELIST_FILE, wl.CACHE_DIR, im.IMAGES_FILE
        wl.WHITELIST_FILE = self.dir / "facts.json"
        im.IMAGES_FILE = self.dir / "images.json"
        wl.CACHE_DIR = self.dir
        im.CACHE_DIR = self.dir
        self.write_facts([fact("F1", "约 1.39 kg", "便携", ["约"])])
        self.write_images()

    def tearDown(self):
        wl.WHITELIST_FILE, wl.CACHE_DIR, im.IMAGES_FILE = self._wf, self._cd, self._if
        im.CACHE_DIR = self._cd
        self.tmp.cleanup()

    def write_facts(self, facts):
        wl.WHITELIST_FILE.write_text(json.dumps({
            "_来源": {"S": {"file": "S.md", "sha256": SRC_SHA, "title": "测试"}}, "facts": facts},
            ensure_ascii=False), encoding="utf-8")

    def write_images(self, n=1):
        imgs = [{"id": "I1", "name": "外观", "file": "i.png", "sha256": IMG_SHA, "source_title": "测试来源",
                 "scope": {"model": "D 14", "year": 2024, "appearance_only": True, "variants": [], "os": []}, "approval": APPROVED}]
        im.IMAGES_FILE.write_text(json.dumps({"images": imgs}, ensure_ascii=False), encoding="utf-8")

    def run_task(self, out, **kw):
        base = dict(product="D14 标准版 Windows", scene="开学季", platform="门店朋友圈", mode="test")
        base.update(kw)
        return pl.run_task(model_client=FakeModel(out), **base)

    # ---- 状态判定 ----
    def test_test_mode_never_qualified(self):
        r = self.run_task(MOMENTS_OK)
        self.assertEqual(r.status, "restricted")
        self.assertIn("测试", r.message)

    def test_cache_mode_good_task_is_qualified(self):
        r = self.run_task(MOMENTS_OK, mode="cache")
        self.assertEqual(r.status, "qualified", [c for c in r.checks if not c["ok"]])

    def test_vague_request_not_generated(self):
        m = FakeModel(MOMENTS_OK)
        r = pl.run_task(free_text="想买轻薄本", model_client=m, mode="cache")
        self.assertEqual(r.status, "need_info")
        self.assertLessEqual(len(r.questions), 3)
        self.assertEqual(m.calls, 0)

    def test_d16_not_written(self):
        m = FakeModel(MOMENTS_OK)
        r = pl.run_task(product="D16", scene="开学季", platform="门店朋友圈", model_client=m, mode="cache")
        self.assertEqual(r.status, "need_info")
        self.assertEqual(m.calls, 0)

    def test_no_approved_facts_fails_without_calling_model(self):
        self.write_facts([dict(fact("F1", "约 1.39 kg", "便携"), approval={"status": "pending", "checked_by": "", "reviewed_by": "", "date": ""})])
        m = FakeModel(MOMENTS_OK)
        r = pl.run_task(product="D14 标准版 Windows", scene="开学季", platform="门店朋友圈", model_client=m, mode="cache")
        self.assertEqual(r.status, "failed")
        self.assertEqual(m.calls, 0)

    # ---- 一张好图 + 错误内容 ≠ 合格 ----
    def test_good_image_but_invented_number_not_qualified(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["article"]["body"][0]["text"] = "重量约 1.39 kg [F1]，续航长达 12 小时。"
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")
        self.assertEqual(r.status, "blocked")

    def test_good_image_but_price_not_qualified(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["article"]["cta"] = "现在只要 3999 元起，国补立减。"
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")

    def test_fact_outside_whitelist_rejected(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["article"]["body"][0]["text"] = "重量约 1.39 kg [F99]。"
        bad["article"]["body"][0]["fact_ids"] = ["F99"]
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")
        self.assertTrue(any(c["name"] == "事实依据" and not c["ok"] for c in r.checks))

    def test_strategy_only_fact_not_allowed_in_body(self):
        self.write_facts([fact("F1", "约 1.39 kg", "便携", ["约"]),
                          fact("C3", "标准版与SE版不能混用", "限制", usage="strategy_only")])
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["article"]["body"][0]["text"] = "重量约 1.39 kg [F1]，标准版与SE版不能混用 [C3]。"
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")

    # ---- 平台结构 ----
    def test_moments_two_selling_points_rejected(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["strategy"]["selected_points"].append({"category": "屏幕", "fact_ids": ["F1"], "why": "x"})
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")

    def test_moments_with_tags_rejected(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["article"]["tags"] = ["#华为"]
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")

    # ---- 图片 ----
    def test_xhs_with_one_image_is_restricted_even_if_text_perfect(self):
        xhs = json.loads(json.dumps(MOMENTS_OK))
        xhs["article"]["title"] = "开学前先想清楚这三件事"
        xhs["article"]["body"] = [
            {"text": "很多新生开学前会纠结带什么电脑。先看携带：重量约 1.39 kg [F1]，依配置而异。" * 2, "fact_ids": ["F1"]},
            {"text": "再看日常使用场景，课间在教室和图书馆之间切换时，机身重量会直接影响心情。" * 2, "fact_ids": []},
            {"text": "选购时请确认版本和系统，部分功能以实际销售版本为准，建议到店亲手确认。" * 2, "fact_ids": []}]
        xhs["article"]["tags"] = ["#开学季", "#笔记本选购", "#大学新生", "#华为"]
        xhs["strategy"]["selected_points"] = [{"category": "便携", "fact_ids": ["F1"], "why": "x"}]
        r = self.run_task(xhs, mode="cache", platform="小红书")
        self.assertEqual(r.status, "restricted", [c for c in r.checks if not c["ok"]])
        self.assertIn("需 3 张，仅有 1 张", r.image_shortage)
        self.assertEqual(len(r.images), 1)

    def test_model_cannot_invent_image(self):
        bad = json.loads(json.dumps(MOMENTS_OK))
        bad["images"] = [{"image_id": "I99", "name": "x", "source": "s", "position": "p", "caption": "c"}]
        r = self.run_task(bad, mode="cache")
        self.assertNotEqual(r.status, "qualified")

    # ---- 失败与限额 ----
    def test_model_failure_is_failed_no_text(self):
        r = self.run_task(ConnectorError("额度已用完", kind="rate_limited"), mode="cache")
        self.assertEqual(r.status, "failed")
        self.assertFalse(r.article)

    def test_model_conflict_is_blocked(self):
        r = self.run_task({"status": "conflict", "detail": "重量两处取值不同"}, mode="cache")
        self.assertEqual(r.status, "blocked")

    # ---- 切换产品后不残留 ----
    def test_switching_to_d16_has_no_d14_facts(self):
        r = pl.run_task(product="D16", scene="开学季", platform="门店朋友圈", model_client=FakeModel(MOMENTS_OK), mode="cache")
        self.assertEqual(r.used_facts, [])
        self.assertEqual(r.images, [])

    # ---- 导出 ----
    def test_export_shows_mode_and_status_on_top(self):
        r = self.run_task(MOMENTS_OK, mode="test")
        txt = pl.to_text(r)
        self.assertTrue(txt.startswith("【状态：受限】【模式：test】"))
        self.assertIn("测试模式", txt)

    def test_export_shows_image_shortage_even_when_content_check_fails(self):
        """朋友圈内容当作小红书输入，平台结构会失败；图片不足的提示仍必须出现在导出里。"""
        r = self.run_task(MOMENTS_OK, mode="cache", platform="小红书")
        self.assertEqual(r.status, "failed")
        self.assertIn("未满足平台要求：需 3 张，仅有 1 张", pl.to_text(r))


class LiveModeTests(PipelineTests):
    """实时模式：读取失败（含限额）= 任务失败，不降级缓存，不调用模型。"""

    class QuotaReader:
        mode = "live"
        stats = {}
        failure = None
        reads = 0

        def read(self, filename, sha):
            from connectors import ConnectorError
            QuotaReaderErr = ConnectorError("资料获取次数已达上限，请明天再尝试", kind="rate_limited", code=220021)
            self.failure = QuotaReaderErr
            type(self).reads += 1
            raise QuotaReaderErr

    def test_live_quota_fails_without_model_and_without_cache(self):
        m = FakeModel(MOMENTS_OK)
        r = pl.run_task(product="D14 标准版 Windows", scene="开学季", platform="门店朋友圈",
                        model_client=m, mode="live", reader=self.QuotaReader())
        self.assertEqual(r.status, "failed")
        self.assertIn("资料读取额度已用完", r.message)
        self.assertEqual(m.calls, 0)
        self.assertFalse(r.article)
        self.assertEqual(r.used_facts, [])


if __name__ == "__main__":
    unittest.main()
