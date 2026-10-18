"""Independent false-positive and true-positive compliance cases."""
import unittest

from app.compliance import check_request, check_text


class ComplianceReviewTests(unittest.TestCase):
    def test_temporal_and_sequence_first_not_marketing_rank(self):
        for text in ("开学第一天去教室", "第一次选购电脑", "第一步确认版本", "第一眼看看外观", "第一台笔记本怎么选才不踩坑？", "最先需要考虑重量", "选购清单第一条：看重量", "第一件要确认的事", "最纠结的是如何选型号"):
            with self.subTest(text=text):
                self.assertFalse(check_request(text))

    def test_audience_worry_is_not_product_superlative(self):
        for text in ("开会最怕接口不匹配", "家长最担心选错", "出差者最关心重量", "你最看重哪一点？", "最关注什么？"):
            with self.subTest(text=text):
                self.assertFalse(check_request(text))

    def test_comparatively_relaxed_not_weight_comparison(self):
        self.assertFalse(check_request("选择之前看看实物，决定时比较轻松"))

    def test_actual_rank_comparison_and_price_still_flagged(self):
        for text in ("行业第一", "全球第一台电脑", "这款很坑", "全网最轻", "性能最强", "比上一代轻很多", "比对手快", "更轻便", "国补立减"):
            with self.subTest(text=text):
                self.assertTrue(check_request(text))

    def test_safe_first_day_does_not_hide_later_rank_claim(self):
        self.assertTrue(check_request("开学第一天。它是行业第一。"))

    def test_weight_does_not_establish_bag_space_or_effort(self):
        for text in ("轻一点包里就能腾出空间", "放进随身包很轻松", "背着不累", "办公更自在"):
            self.assertTrue(check_request(text), text)

    def test_full_approved_weight_disclosure_is_required(self):
        disclosure = "实际重量依配置、制造工艺、测量方法的不同可能有所差异。"
        fact = {"id": "SYNTHETIC-F", "value": "约 1.39 kg", "must_keep": ["约", disclosure]}
        self.assertTrue(check_text("重量约 1.39 kg [SYNTHETIC-F]", [fact]))
        self.assertFalse(check_text("重量约 1.39 kg [SYNTHETIC-F]，" + disclosure, [fact]))

    def test_qualifier_in_same_paragraph_not_lost_at_character_boundary(self):
        fact = {"id": "F1", "value": "100% sRGB", "must_keep": ["典型值"]}
        text = "典型值为 100% sRGB。" + "选购前可结合自己的文档需求，向门店确认具体销售配置。" * 3 + "[F1]"
        self.assertFalse(check_text(text, [fact]))
        self.assertTrue(check_text("典型值为 100% sRGB。\n另一段 100% sRGB [F1]", [fact]))

    def test_asking_which_model_fits_is_not_itself_a_comparison_claim(self):
        self.assertFalse(check_request("不确定哪款更适合自己？欢迎到店确认。"))
        self.assertTrue(check_request("不确定哪款更适合自己？这台更适合你。"))


if __name__ == "__main__":
    unittest.main()
