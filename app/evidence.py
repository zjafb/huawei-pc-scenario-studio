"""Shared evidence validation. No function grants human approval."""
from __future__ import annotations

import re
from datetime import date


def approval_issue(approval: dict) -> str:
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        return "尚未完成人工批准。"
    people = [str(approval.get(k) or "").strip() for k in ("checked_by", "reviewed_by")]
    placeholders = {"-", "_", "none", "null", "n/a", "todo", "unknown", "待签字", "待确认", "未填写", "待填写", "待复核", "codex", "claude", "chatgpt", "ai"}
    if any(not p or p.lower() in placeholders or set(p) <= {"_", "-", "?", "？"} for p in people):
        return "需填写真实核对人和独立复核人，不能用占位内容或 AI 代签。"
    if people[0].casefold() == people[1].casefold():
        return "核对人与独立复核人必须不同。"
    for field in ("date", "reviewed_date"):
        value = approval.get(field)
        if field == "reviewed_date" and value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return "核对日期必须为有效的 YYYY-MM-DD。"
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            return "核对日期必须为有效的 YYYY-MM-DD。"
    return ""


def scope_covers(scope: dict, task) -> tuple[bool, str, str]:
    if not isinstance(scope, dict) or not scope.get("model") or not scope.get("year"):
        return False, "来源没有明确型号和年份，视为未知，不放行。", "scope_unknown"
    if scope["model"] != task.model or scope["year"] != task.year:
        return False, "来源型号或年份与本次任务不符（仅本次排除，原批准不变）。", "out_of_scope"
    for field, target, label in (("variants", task.variant, "版本"), ("os", task.os, "系统")):
        values = scope.get(field)
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
            return False, f"来源未明确覆盖哪些{label}，不能作为通配范围。", "scope_unknown"
        if target is None or not str(target).strip():
            return False, f"本次尚未明确{label}，请先选择。", "scope_unknown"
        if target not in values:
            return False, f"来源不覆盖本次{label}（仅本次排除，原批准不变）。", "out_of_scope"
    return True, "来源范围明确覆盖本次目标配置。", "ok"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def quote_issue(fact: dict, source_text: str) -> str:
    quotes = fact.get("quotes")
    if quotes is None:
        quotes = [fact.get("quote")]
    if not isinstance(quotes, list) or not quotes or any(not isinstance(q, str) or not q.strip() for q in quotes):
        return "事实缺少非空原文引用。"
    if any(q not in source_text for q in quotes):
        return "事实引用不是已验证原文的完整子串。"
    source = _compact(source_text)
    keep = fact.get("must_keep") or []
    if not isinstance(keep, list) or any(not isinstance(k, str) or not k.strip() or _compact(k) not in source for k in keep):
        return "事实限定条件没有原文依据。"
    value = fact.get("value")
    if not isinstance(value, str) or not value.strip():
        return "事实值为空。"
    def qualifier(match):
        return "" if any(_compact(k) in _compact(match.group(0)) for k in keep) else match.group(0)
    value = re.sub(r"[（(][^）)]*[）)]", qualifier, value)
    quoted = _compact("\n".join(quotes))
    chunks = [c.strip() for c in re.split(r"[、，,；;\n]", value) if c.strip()]
    if any(_compact(chunk) not in quoted for chunk in chunks):
        return "引用未覆盖事实值的全部组成部分；请拆分事实或补齐逐项原文引用。"
    return ""
