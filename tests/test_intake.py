import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.intake import resolve  # noqa: E402


class IntakeTests(unittest.TestCase):
    def test_vague_request_asks_at_most_three_and_does_not_generate(self):
        it = resolve(free_text="想买轻薄本")
        self.assertIn(it.status, ("need_info", "need_choice"))
        self.assertGreaterEqual(len(it.questions), 1)
        self.assertLessEqual(len(it.questions), 3)
        self.assertIsNone(it.model)

    def test_d14_alone_asks_for_version_and_os(self):
        it = resolve(product="D14", scene="开学季", platform="门店朋友圈")
        self.assertEqual(it.model, "D 14")
        self.assertEqual(it.choices.get("variant"), ["标准版", "SE 版"])
        self.assertEqual(it.choices.get("os"), ["Windows", "Linux"])
        self.assertNotEqual(it.status, "ok")

    def test_full_d14_task_is_ok(self):
        it = resolve(product="MateBook D 14 标准版 Windows", scene="开学季", platform="门店朋友圈",
                     audience="大学新生")
        self.assertEqual((it.status, it.model, it.variant, it.os, it.scene, it.platform),
                         ("ok", "D 14", "标准版", "Windows", "school", "moments"))

    def test_two_models_requires_choice(self):
        it = resolve(product="D14 和 D16", scene="开学季", platform="小红书")
        self.assertIsNone(it.model)
        self.assertEqual(it.choices["model"], ["D 14", "D 16"])

    def test_unknown_model_is_unsupported_not_guessed(self):
        it = resolve(product="MateBook X Pro", scene="开学季", platform="小红书")
        self.assertEqual(it.status, "unsupported")
        self.assertIsNone(it.model)

    def test_official_account_and_poster_unsupported(self):
        it = resolve(product="D14", scene="开学季", platform="公众号")
        self.assertEqual(it.status, "unsupported")

    def test_scene_inferred_from_free_text(self):
        it = resolve(product="D14 标准版 Windows", free_text="给经常出差的商务人士发朋友圈")
        self.assertEqual((it.scene, it.platform), ("business", "moments"))

    def test_missing_audience_gets_visible_assumption(self):
        it = resolve(product="D14 SE版 Windows", scene="开学季", platform="小红书")
        self.assertTrue(any("假设" in n for n in it.notes))

    def test_d16_not_asked_for_variant(self):
        it = resolve(product="D16", scene="开学季", platform="小红书")
        self.assertEqual(it.model, "D 16")
        self.assertNotIn("variant", it.choices)


if __name__ == "__main__":
    unittest.main()
