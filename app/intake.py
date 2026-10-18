"""输入补问与型号确认。纯规则，不调用模型：缺项就问，歧义就让用户选，不自己猜。

对应 docs/prelim-design.md 第 5 节第 2、3 步，final-plan 验收 1、2。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SUPPORTED_PLATFORMS = {"moments": "门店朋友圈", "xhs": "小红书"}
SUPPORTED_SCENES = {"school": "开学季", "business": "职场差旅"}

# 型号别名。只收录已核对范围内的型号；其他型号一律提示“未纳入已核范围”。
MODEL_ALIASES = {
    "D 14": ["d14", "d 14", "matebook d 14", "matebookd14", "d14 2024", "matebook d14"],
    "D 16": ["d16", "d 16", "matebook d 16", "matebookd16", "d16 2024", "matebook d16"],
}

# 看起来像华为 PC 型号，但不在已核范围
OTHER_MODEL_PATTERN = re.compile(
    r"(matebook\s*(x\s*pro|14s?|16s?|e|gt|fold|pro)|mate\s*book\s*(x|e)|\bx\s*pro\b|擎云|mateStation|matestation)", re.I)

VAGUE_PRODUCT = re.compile(r"(轻薄本|笔记本|电脑|华为电脑|华为pc|pc|本子)", re.I)


@dataclass
class Intake:
    status: str                      # ok | need_info | need_choice | unsupported
    model: str | None = None
    variant: str | None = None
    os: str | None = None
    scene: str | None = None         # school | business
    platform: str | None = None      # moments | xhs
    audience: str = ""
    questions: list[str] = field(default_factory=list)
    choices: dict[str, list[str]] = field(default_factory=dict)   # 字段 → 候选
    notes: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def detect_model(text: str) -> tuple[str | None, bool]:
    """返回 (型号, 是否同时出现多个型号)。"""
    t = text or ""
    found = [f"D {number}" for number in (14, 16)
             if re.search(rf"(?<![A-Za-z0-9])(?:matebook\s*)?d\s*{number}(?![A-Za-z0-9])", t, re.I)]
    return (found[0] if len(found) == 1 else None), len(found) > 1


def detect_variant(text: str) -> str | None:
    t = text or ""
    if re.search(r"SE\s*版|\bSE\b", t, re.I):
        return "SE 版"
    if "标准版" in t:
        return "标准版"
    return None


def detect_os(text: str) -> str | None:
    t = text or ""
    if re.search(r"linux", t, re.I):
        return "Linux"
    if re.search(r"windows|win\s*11|win11", t, re.I):
        return "Windows"
    return None


def resolve(*, product: str = "", audience: str = "", scene: str = "", platform: str = "",
            free_text: str = "", variant: str = "", os_name: str = "") -> Intake:
    """把用户输入整理成任务。顺序：平台 → 场景 → 产品 → 版本。最多 3 个追问。"""
    blob = " ".join([product, audience, scene, platform, free_text])
    it = Intake(status="ok", audience=audience.strip())
    years = set(re.findall(r"(?<!\d)20\d{2}(?!\d)", product + " " + free_text))
    if years and years != {"2024"}:
        it.status = "unsupported"
        it.notes.append("初赛已核资料只覆盖 2024 款；你输入了其他年份，请明确选择 2024 款后再生成。")
        return it

    # 平台
    plat = platform.strip()
    for key, name in SUPPORTED_PLATFORMS.items():
        if plat in (key, name) or (plat and plat in name):
            it.platform = key
    if not it.platform:
        if re.search(r"朋友圈", blob):
            it.platform = "moments"
        elif re.search(r"小红书", blob):
            it.platform = "xhs"
        elif re.search(r"公众号|海报", blob):
            it.status = "unsupported"
            it.notes.append("初赛版本暂不支持公众号和门店海报，请改选门店朋友圈或小红书。")
            return it

    # 场景
    sc = scene.strip()
    for key, name in SUPPORTED_SCENES.items():
        if sc in (key, name) or (sc and sc in name):
            it.scene = key
    if not it.scene:
        if re.search(r"开学|新生|大学|学生|家长", blob):
            it.scene = "school"
        elif re.search(r"出差|差旅|商务|职场|会议|办公", blob):
            it.scene = "business"

    # 产品
    model, multiple = detect_model(blob)
    if multiple:
        it.choices["model"] = ["D 14", "D 16"]
        it.questions.append("你提到了不止一个型号，这次要推哪一款？（D 14 / D 16）")
    elif model:
        it.model = model
    elif OTHER_MODEL_PATTERN.search(blob):
        it.status = "unsupported"
        it.notes.append("该型号未纳入初赛已核范围（目前只支持 MateBook D 14 2024；D 16 仅用于型号切换测试）。")
        return it
    else:
        it.choices["model"] = ["D 14", "D 16"]
        it.questions.append("请确认完整型号：MateBook D 14 2024 还是 D 16 2024？其他型号暂未纳入已核范围。")

    # 版本与系统（仅 D 14 需要问；D 16 不成稿）
    has_standard = "标准版" in blob
    has_se = bool(re.search(r"SE\s*版|\bSE\b", blob, re.I))
    has_windows = bool(re.search(r"windows|win\s*11", blob, re.I))
    has_linux = bool(re.search(r"linux", blob, re.I))
    it.variant = variant if variant in ("标准版", "SE 版") else (None if has_standard and has_se else detect_variant(blob))
    it.os = os_name if os_name in ("Windows", "Linux") else (None if has_windows and has_linux else detect_os(blob))
    if variant and variant not in ("标准版", "SE 版"):
        it.variant = None
    if os_name and os_name not in ("Windows", "Linux"):
        it.os = None
    if it.model == "D 14":
        if not it.variant:
            it.choices["variant"] = ["标准版", "SE 版"]
            it.questions.append("D 14 有标准版和 SE 版，屏幕色域、键盘不同，你要写哪一版？")
        if not it.os:
            it.choices["os"] = ["Windows", "Linux"]
            it.questions.append("是 Windows 版还是 Linux 版？（部分功能只有 Windows 版有）")

    # 缺项
    if not it.platform:
        it.choices["platform"] = list(SUPPORTED_PLATFORMS.values())
        it.questions.append("要发在哪里？门店朋友圈还是小红书？")
    if not it.scene:
        it.choices["scene"] = list(SUPPORTED_SCENES.values())
        it.questions.append("面向什么场景？开学季（新生）还是职场差旅？")
    if not it.audience:
        it.audience = {"school": "大学新生", "business": "经常出差的职场人"}.get(it.scene or "", "")
        if it.audience:
            it.notes.append(f"人群未填写，按场景默认假设为「{it.audience}」，可在页面修改。")

    if it.questions:
        it.status = "need_choice" if (it.choices and it.model is None) or any(
            k in it.choices for k in ("variant", "os")) else "need_info"
        it.questions = it.questions[:3]
    return it
