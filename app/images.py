"""图片选择：只用已批准、原图存在且指纹一致、范围匹配的图片。数量不足就如实说，不凑数。

对应 docs/prelim-design.md 第 6 节。图片数量只是“合格”的一个子项，本模块不判定整体状态。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from connectors import ConnectorError, VerifiedCache

from .whitelist import CACHE_DIR, ROOT, WHITELIST_DIR, Task
from .evidence import approval_issue

IMAGES_FILE = WHITELIST_DIR / "images.json"

PLATFORM_IMAGE_RANGE = {"moments": (1, 3), "xhs": (3, 6)}


@dataclass
class ImageDecision:
    image_id: str
    allowed: bool
    reason: str
    kind: str   # ok | not_approved | file_missing | source_changed | out_of_scope


@dataclass
class ImageResult:
    selected: list[dict] = field(default_factory=list)
    decisions: list[ImageDecision] = field(default_factory=list)
    needed_min: int = 0
    needed_max: int = 0
    payloads: dict[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def count(self) -> int:
        return len(self.selected)

    @property
    def enough(self) -> bool:
        """图片子项是否满足平台最低要求。这不等于任务合格。"""
        return self.count >= self.needed_min

    def shortage_text(self) -> str:
        if self.enough:
            return ""
        return f"未满足平台要求：需 {self.needed_min} 张，仅有 {self.count} 张"


def load_raw() -> dict:
    if not IMAGES_FILE.exists():
        return {"images": []}
    return json.loads(IMAGES_FILE.read_text(encoding="utf-8"))


def _in_scope(scope: dict, task: Task) -> bool:
    """图片范围必须写明。空 variants/os 不再当“全版本通用”：
    要么写出明确覆盖的版本和系统，要么 appearance_only=true 表示仅外观示意、不对应具体配置。"""
    if scope.get("model") != task.model or scope.get("year") != task.year:
        return False
    if scope.get("appearance_only") is True:
        return True
    variants = scope.get("variants") or []
    oses = scope.get("os") or []
    if not variants or not oses:          # 未写明 → 未知，不放行
        return False
    return task.variant in variants and task.os in oses


def select_images(task: Task, platform: str, cache=None, reader=None) -> ImageResult:
    """reader 同 build_fact_pool：实时任务传 LiveSourceReader。"""
    lo, hi = PLATFORM_IMAGE_RANGE.get(platform, (0, 0))
    res = ImageResult(needed_min=lo, needed_max=hi)
    cache = reader or cache or VerifiedCache(CACHE_DIR)

    seen_hashes: set[str] = set()
    for img in load_raw().get("images", []):
        iid = img["id"]
        appr = img.get("approval", {})
        issue = approval_issue(appr)
        if issue:
            res.decisions.append(ImageDecision(iid, False, issue, "not_approved"))
            continue
        if img.get("conclusion") not in (None, "usable", "可用"):
            res.decisions.append(ImageDecision(iid, False, "图片结论不是可用，不能因签字字段存在而放行。", "not_approved"))
            continue
        if appr.get("source_sha256") and appr["source_sha256"] != img.get("sha256"):
            res.decisions.append(ImageDecision(iid, False, "原图指纹与人工批准时不同，需重新核对。", "source_changed"))
            continue
        if not _in_scope(img.get("scope", {}), task):
            res.decisions.append(ImageDecision(iid, False, "图片适用范围与本次任务不匹配（仅本次排除，批准不变）。", "out_of_scope"))
            continue
        try:
            content = cache.read(img["file"], img["sha256"])
        except ConnectorError as e:
            kind = "file_missing" if e.kind == "cache_missing" else "source_changed"
            msg = "原图文件缺失，没有原图就算不足，不借图。" if kind == "file_missing" else f"原图校验失败：{e}"
            res.decisions.append(ImageDecision(iid, False, msg, kind))
            continue
        if img["sha256"] in seen_hashes:      # 不重复同一张图凑数
            res.decisions.append(ImageDecision(iid, False, "与已选图片内容重复，不凑数。", "out_of_scope"))
            continue
        seen_hashes.add(img["sha256"])
        res.selected.append(dict(img))
        res.payloads[iid] = content.data
        res.decisions.append(ImageDecision(iid, True, "已批准、原图存在、指纹一致、范围匹配。", "ok"))
        if res.count >= hi:
            break
    return res
