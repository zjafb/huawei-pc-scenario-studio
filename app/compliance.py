"""合规检查：规则优先，不靠模型一句“通过”。词库对应 rules/compliance.md。

两个入口：
- check_request(text)：用户额外要求（“加国补立减”）。命中拦截类 → blocked，并给出原因。
- check_text(text, allowed_facts)：成稿正文。逐类扫描，返回命中项与处理动作。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Hit:
    category: str     # 类别名
    word: str         # 命中的词
    action: str       # block | rewrite
    reason: str
    sentence: str = ""


# ---- 词库（与 rules/compliance.md 一一对应）----
ABSOLUTE = ["全网最", "全国最", "行业最", "史上最", "业内最", "最轻", "最薄", "最强", "最快", "最好", "最佳",
            "最适合", "最便宜", "最实惠", "第一", "No.1", "顶级", "顶尖", "极致", "完美", "无敌", "碾压",
            "独一无二", "唯一", "绝无仅有", "领先同行", "遥遥领先", "秒杀", "吊打"]

PROMISE = ["保证", "一定能", "一定会", "绝对", "百分百", "包过", "永久", "终身", "无限", "零故障", "永不卡顿",
           "永远流畅", "不卡顿", "不发热", "不会坏", "包退", "包换", "无条件退", "秒开", "一键解决", "必买",
           "所有设备", "所有课程"]

PRICE = ["价格", "售价", "现价", "原价", "特价", "低至", "仅需", "只要", "立减", "直降", "满减", "优惠", "折扣",
         "补贴", "国补", "学生优惠", "教育优惠", "赠品", "赠送", "买就送", "免息", "分期", "0元", "元起", "￥", "¥",
         "RMB", "限时", "活动价", "到手价", "性价比之王", "便宜", "免费"]
PRICE_PATTERNS = [r"\d+\s*元", r"\d+\s*折", r"立减\s*\d+"]

COMPARE = ["比上一代", "比前代", "比旧款", "比去年", "更轻", "更薄", "更快", "更强", "更长", "超越", "胜过",
           "优于", "强于", "不输", "轻一点", "更高效", "更舒适", "更简单"]
COMPARE_PATTERNS = [r"比(?!较轻松).{0,6}(快|轻|薄|强|长)(很多|不少|一倍|得多)?",
                    r"(?<!哪款)(?<!哪台)(?<!哪个)(?<!哪一款)更适合"]

DISPARAGE = ["苹果", "MacBook", "联想", "戴尔", "小米", "竞品", "别家", "其他品牌", "别的电脑", "劣质", "垃圾",
             "智商税", "坑人", "坑货", "太坑", "很坑"]

FAKE_EXPERIENCE = ["我用了", "我买了", "我入手", "入手后", "亲测", "实测", "真实体验", "使用一个月", "用了半年",
                   "用了一个学期", "我同学", "我室友", "室友都", "朋友推荐", "好评如潮", "满分好评", "销量第一",
                   "爆款", "热销", "畅销", "榜首", "获奖", "荣获", "权威认证", "专家推荐", "老师推荐", "学校指定"]

HEALTH = ["保护视力", "防近视", "不伤眼", "缓解疲劳", "治疗", "改善视力", "能护眼", "有效护眼"]
UNSUPPORTED_BENEFITS = ["腾出空间", "省下空间", "放进随身包很轻松", "背着不累", "办公更自在", "显示效果清晰"]

# 数字+单位：必须在已批准事实中找到。结构性数字（“三个”“两个”）不检查。
UNIT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(小时|分钟|秒钟?|倍|%|GB|TB|Wh|W|kg|g|克|mm|英寸|寸|nits|Hz|MHz|GHz|核|代)", re.I)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]", text)
    return [p.strip() for p in parts if p.strip()]


def _find_sentence(text: str, word: str) -> str:
    for s in _sentences(text):
        if word in s:
            return s
    return ""


def _scan(text: str, words: list[str], category: str, action: str, reason: str) -> list[Hit]:
    hits = []
    for w in words:
        if w in text:
            hits.append(Hit(category, w, action, reason, _find_sentence(text, w)))
    return hits


def _scan_patterns(text: str, pats: list[str], category: str, action: str, reason: str) -> list[Hit]:
    hits = []
    for p in pats:
        for m in re.finditer(p, text):
            hits.append(Hit(category, m.group(0), action, reason, _find_sentence(text, m.group(0))))
    return hits


def _absolute_hits(text: str) -> list[Hit]:
    hits = _scan(text, [w for w in ABSOLUTE if w != "第一"], "绝对化宣传", "rewrite", "绝对化用语，无法证明，需删除或改为有依据的陈述")
    # Ordinary temporal/sequence phrases are not product-rank claims.
    for m in re.finditer(r"第一", text):
        if text[m.end():].startswith(tuple("天次周月年步章节眼条项点件个台部本款")) and not re.search(
                r"全球|世界|全国|国内|行业|全网|首创", text[max(0, m.start() - 10):m.start()]):
            continue
        start = max(text.rfind(c, 0, m.start()) for c in "。！？!?；;\n") + 1
        end = re.search(r"[。！？!?；;\n]", text[m.end():])
        sentence = text[start:m.end() + end.start()] if end else text[start:]
        hits.append(Hit("绝对化宣传", "第一", "rewrite", "未经证明的排名用语", sentence.strip()))
    # Explicit product/rank attributes avoid treating every audience feeling
    # (最纠结、最先考虑、最担心) as an advertising superlative.
    attributes = "轻|薄|快|强|好|佳|适合|合适|便宜|实惠|优秀|省电|耐用|清晰|流畅|稳定|安全|智能|先进|舒适|高效|便携|专业|全面|划算|可靠|强悍|持久|省心|受欢迎|值得买|出色|领先|节能|优|棒|高端|低价"
    for m in re.finditer(r"最(?:" + attributes + r")", text):
        w = m.group(0)
        if not any(h.word in w or w in h.word for h in hits):
            hits.append(Hit("绝对化宣传", w, "rewrite", "极限词，无法证明", _find_sentence(text, w)))
    return hits


def check_request(text: str) -> list[Hit]:
    """用户额外要求。价格、竞品贬低、伪造体验 → 直接拦截；其余 → 改写。"""
    hits: list[Hit] = []
    price_reason = "知识库中没有已批准的价格或补贴依据，不能写，写上去可能误导顾客"
    hits += _scan(text, PRICE, "价格误导", "block", price_reason)
    hits += _scan_patterns(text, PRICE_PATTERNS, "价格误导", "block", price_reason)
    hits += _scan(text, DISPARAGE, "竞品贬低", "block", "不得提及、比较或贬低其他品牌或产品")
    hits += _scan(text, FAKE_EXPERIENCE, "伪造体验", "block", "不得编造个人体验、评价、销量或奖项")
    hits += _scan(text, PROMISE, "虚假承诺", "block", "无法保证的承诺")
    hits += _absolute_hits(text)
    hits += _scan(text, COMPARE, "无依据对比", "block", "没有已批准的对比事实，不能比较")
    hits += _scan_patterns(text, COMPARE_PATTERNS, "无依据对比", "block", "没有已批准的对比事实，不能比较")
    hits += _scan(text, HEALTH, "功效宣称", "rewrite", "不得宣称对视力等的功效")
    hits += _scan(text, UNSUPPORTED_BENEFITS, "无依据场景承诺", "rewrite", "已批准的重量或外观不能证明装包空间、体感或办公效果")
    return _dedupe(hits)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def check_text(text: str, allowed_facts: list[dict], *, platform: str = "") -> list[Hit]:
    """成稿正文。除词库外，还检查数字+单位是否对应到已批准事实，以及必须保留的限定条件。"""
    hits = check_request(text)

    # 数字+单位必须能在已批准事实的 value/quote 中找到
    fact_blob = _norm(" ".join(f"{f.get('value','')} {f.get('quote','')}" for f in allowed_facts))
    for m in UNIT_PATTERN.finditer(text):
        token = _norm(m.group(0))
        if token not in fact_blob:
            hits.append(Hit("无依据数字", m.group(0), "block",
                            "该数据没有已批准依据（数字+单位不在已批准事实中）", _find_sentence(text, m.group(0))))

    # 事实的限定条件必须保留（如“约”“典型值”“仅限 Windows”）
    for f in allowed_facts:
        marker = f"[{f['id']}]"
        if marker not in text:
            continue
        window = _window_around(text, marker)
        for keep in f.get("must_keep", []):
            if keep not in window:
                hits.append(Hit("丢失限定条件", f"{f['id']}:{keep}", "rewrite",
                                f"事实 {f['id']} 必须保留限定「{keep}」", window))

    # 小红书：禁止第一人称体验已在 FAKE_EXPERIENCE；这里加“我”开头的体验句
    if platform == "xhs":
        for s in _sentences(text):
            if re.match(r"^我(?!们)", s) and re.search(r"(用|买|入手|试|体验|觉得|发现)", s):
                hits.append(Hit("伪造体验", s[:12], "block", "小红书不得伪造个人体验", s))
    return _dedupe(hits)


def _window_around(text: str, marker: str, span: int = 40) -> str:
    i = text.find(marker)
    if i < 0:
        return ""
    # A disclosure belongs to the cited paragraph, not an arbitrary character radius.
    start = text.rfind("\n", 0, i) + 1
    end = text.find("\n", i)
    return text[start:end if end >= 0 else len(text)]


def _dedupe(hits: list[Hit]) -> list[Hit]:
    seen, out = set(), []
    for h in hits:
        key = (h.category, h.word)
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def summarize(hits: list[Hit]) -> dict:
    blocked = [h for h in hits if h.action == "block"]
    rewrite = [h for h in hits if h.action == "rewrite"]
    return {"blocked": blocked, "rewrite": rewrite, "clean": not hits}
