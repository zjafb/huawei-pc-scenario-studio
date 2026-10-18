"""白名单：只有人工批准、来源指纹一致、范围覆盖目标配置的事实和图片才能进入成稿。

设计要点（对应 docs/prelim-design.md 4.2、4.3、4.6）：
- 批准失效（来源指纹变了）与本任务排除（型号/版本/系统不匹配）是两回事。
- 来源范围未知时不放行，不能当通配符。
- 本模块不替任何人批准；status 只读自 JSON。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from connectors import ConnectorError, VerifiedCache
from .evidence import approval_issue, quote_issue, scope_covers

ROOT = Path(__file__).resolve().parent.parent
WHITELIST_DIR = Path(os.environ.get("APP_WHITELIST_DIR", str(ROOT / "data" / "whitelist")))
WHITELIST_FILE = WHITELIST_DIR / "facts.json"
CACHE_DIR = Path(os.environ.get("APP_CACHE_DIR", str(ROOT / "data" / "private" / "ima-cache")))


@dataclass
class Task:
    """一次任务的目标产品范围。None 表示用户尚未指定（此时依赖版本的事实不放行）。"""
    model: str                       # 如 "D 14"
    year: int = 2024
    variant: str | None = None       # "标准版" / "SE 版" / None
    os: str | None = None            # "Windows" / "Linux" / None


@dataclass
class Decision:
    fact_id: str
    allowed: bool
    reason: str                      # 给人看的原因
    kind: str                        # ok | not_approved | source_changed | out_of_scope | scope_unknown


@dataclass
class FactPool:
    allowed: list[dict] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    mode: str = "cache"
    cache_note: str = ""

    def pending_report(self) -> list[Decision]:
        return [d for d in self.decisions if not d.allowed and d.kind != "out_of_scope"]


def load_raw() -> dict:
    if not WHITELIST_FILE.exists():
        return {"_来源": {}, "facts": []}
    return json.loads(WHITELIST_FILE.read_text(encoding="utf-8"))


def _scope_covers(scope: dict, task: Task) -> tuple[bool, str, str]:
    """来源范围是否明确覆盖目标配置。返回 (是否覆盖, 原因, 类别)。"""
    return scope_covers(scope, task)


def build_fact_pool(task: Task, cache=None, reader=None) -> FactPool:
    """reader 是通用来源读取器，需有 read(filename, sha256) 与 mode 属性。
    实时任务传 LiveSourceReader（每次任务新建）；测试传 VerifiedCache。
    参数 cache 保留旧名只为兼容，含义同 reader。"""
    data = load_raw()
    sources = data.get("_来源", {})
    reader = reader or cache or VerifiedCache(CACHE_DIR)
    cache = reader
    mode = getattr(reader, "mode", "cache")
    notes = {"live": "实时：本次任务已从 ima 读取原文并核对指纹。",
             "cache": "测试/缓存：使用本地原文，未验证远端当前最新。"}
    pool = FactPool(mode=mode, cache_note=notes.get(mode, ""))

    # 先校验每个来源的指纹（A：批准失效的判断）
    source_ok: dict[str, tuple[bool, str]] = {}
    source_texts: dict[str, str] = {}
    for key, meta in sources.items():
        try:
            source_texts[key] = cache.read(meta["file"], meta["sha256"]).text()
            source_ok[key] = (True, "")
        except ConnectorError as e:
            source_ok[key] = (False, f"来源「{meta.get('title', key)}」校验失败：{e}。需重新核对。")

    for fact in data.get("facts", []):
        fid = fact["id"]
        appr = fact.get("approval", {})

        # 1. 必须逐条人工批准且有两人签字
        if issue := approval_issue(appr):
            pool.decisions.append(Decision(fid, False, issue, "not_approved"))
            continue

        approved_sha = appr.get("source_sha256")
        current_sha = sources.get(fact.get("source"), {}).get("sha256")
        if approved_sha and approved_sha != current_sha:
            pool.decisions.append(Decision(fid, False, "来源清单指纹与人工批准时不同，需重新核对。", "source_changed"))
            continue

        # 2. 来源指纹（批准失效）
        ok, why = source_ok.get(fact["source"], (False, "来源未登记。"))
        if not ok:
            pool.decisions.append(Decision(fid, False, why, "source_changed"))
            continue

        # 3. 范围（本任务排除）
        covered, why, kind = _scope_covers(fact.get("scope", {}), task)
        if not covered:
            pool.decisions.append(Decision(fid, False, why, kind))
            continue

        if fact.get("conclusion", "usable") not in ("usable", "可用"):
            pool.decisions.append(Decision(fid, False, "该事实结论不是可用，不能进入事实池。", "not_usable"))
            continue
        if issue := quote_issue(fact, source_texts.get(fact["source"], "")):
            pool.decisions.append(Decision(fid, False, issue, "invalid_quote"))
            continue
        meta = sources[fact["source"]]
        pool.allowed.append({**fact, "source_title": meta.get("title", fact["source"]),
                             "source_sha256": meta["sha256"], "source_file": meta["file"]})
        pool.decisions.append(Decision(fid, True, why, "ok"))
    return pool
