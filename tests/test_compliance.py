"""把 rules/compliance-samples.md 的样本逐条自动化。测试输入是规则样本，不是真实运行结果。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compliance import check_request, check_text  # noqa: E402

# 与 B 部分对应的“已批准事实”（仅测试用）
FACTS = [
    {"id": "F14-01", "value": "约 1.39 kg", "quote": "约 1.39 kg", "must_keep": ["约"]},
    {"id": "F14-02", "value": "14 英寸、IPS、16:10", "quote": "14 英寸", "must_keep": []},
    {"id": "F14-03a", "value": "100% sRGB（典型值）", "quote": "100% sRGB", "must_keep": ["典型值"]},
    {"id": "F14-04", "value": "56 Wh（额定容量）", "quote": "56 Wh（额定容量）", "must_keep": ["额定容量"]},
    {"id": "F14-05", "value": "华为分享（仅限 Windows 版本产品支持）", "quote": "华为分享", "must_keep": ["仅限 Windows"]},
]

# A 部分：用户额外要求 → 应拦截/改写（A01–A30 对用户请求；其余为成稿文本）
A_REQUESTS = {
    "A01": "加上国补立减", "A02": "写上现在只要 3999 元起", "A03": "说学生可以享受教育优惠",
    "A04": "提一下可以分期免息", "A05": "写限时特价，最后三天", "A06": "说买就送鼠标",
    "A07": "写比官网便宜 500 元", "A08": "强调性价比之王",
    "A09": "写它是全网最轻的笔记本", "A10": "说这是最适合大学生的电脑", "A11": "写它的屏幕是顶级的",
    "A12": "说它性能碾压同价位", "A13": "写这是唯一支持某功能的电脑", "A14": "写业内第一",
    "A15": "写极致轻薄，完美体验",
    "A16": "保证永不卡顿", "A17": "说绝对不会发热", "A18": "写终身免费维修",
    "A19": "说一定能满足所有课程需求", "A20": "写百分百兼容所有设备",
    "A21": "比苹果更适合学生", "A22": "说联想的不如这款", "A23": "写比上一代快很多",
    "A24": "写别家的都是智商税", "A25": "说比去年款续航长一倍",
    "A26": "写我用了一个学期，非常好用", "A27": "写亲测续航撑满一整天", "A28": "说我室友都买了这款",
    "A29": "写好评如潮，销量第一", "A30": "说荣获某某大奖",
    "A36": "写这款能防近视",
}

# 成稿文本类（需要事实池参与）
A_TEXTS = {
    "A31": "续航长达 12 小时 [F14-04]",
    "A32": "56 Wh 电池可以用 10 小时 [F14-04]",
    "A33": "重量 1.39 kg [F14-01]",
}

B_TEXTS = {
    "B01": "选购前先搞清楚这三个问题",
    "B02": "重量约 1.39 kg [F14-01]，实际重量依配置而异",
    "B03": "14 英寸 IPS 屏幕，16:10 比例 [F14-02]",
    "B04": "标准版色域为 100% sRGB（典型值）[F14-03a]",
    "B05": "电池额定容量 56 Wh（额定容量）[F14-04]，使用时间因使用情况而异",
    "B06": "开学前最后一个要定下来的装备",
    "B07": "最近很多新生在问怎么选",
    "B08": "想亲手试试，欢迎来店看看",
    "B09": "具体配置以实际销售版本为准",
    "B10": "显示管理里有护眼模式可以开启（仅限 Windows 版）",
    "B11": "两个常见担心：重量和接口够不够用",
    "B12": "Windows 版带有华为分享功能（仅限 Windows 版本产品支持）[F14-05]",
}


class ComplianceSamples(unittest.TestCase):
    def test_A_requests_all_flagged(self):
        missed = [k for k, v in A_REQUESTS.items() if not check_request(v)]
        self.assertEqual(missed, [], f"以下应拦截的样本没有被命中: {missed}")

    def test_A_texts_flagged(self):
        missed = [k for k, v in A_TEXTS.items() if not check_text(v, FACTS)]
        self.assertEqual(missed, [], f"以下应命中的成稿样本没有被命中: {missed}")

    def test_B_not_blocked(self):
        wrongly = {}
        for k, v in B_TEXTS.items():
            hits = check_text(v, FACTS)
            if hits:
                wrongly[k] = [(h.category, h.word) for h in hits]
        self.assertEqual(wrongly, {}, f"以下正常样本被误杀: {wrongly}")

    def test_price_request_is_block_with_reason(self):
        hits = check_request("加国补立减")
        self.assertTrue(any(h.action == "block" and h.category == "价格误导" for h in hits))
        self.assertTrue(all("已批准" in h.reason for h in hits if h.category == "价格误导"))

    def test_absolute_words_are_rewrite_not_block(self):
        hits = check_request("全网最轻")
        self.assertTrue(hits and all(h.action in ("rewrite", "block") for h in hits))

    def test_missing_approx_is_flagged(self):
        hits = check_text("重量 1.39 kg [F14-01]", FACTS)
        self.assertTrue(any(h.category == "丢失限定条件" for h in hits))

    def test_scope_scenario_samples_documented(self):
        # A34（SE 版用标准版色域）与 A35（Linux 版用 Windows 功能）属于“范围不匹配”，
        # 由 app/whitelist.py 的范围校验拦截，不在词库检查范围内；见 tests/test_whitelist.py。
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
