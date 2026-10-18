"""Isolated prompt test: synthetic facts + real model, never IMA/cache input.

Requires --run to make exactly two ModelScope calls. Outputs remain private and
are explicitly ineligible as real marketing results or team-approved evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.compliance import check_text
from app.images import ImageResult
from app.intake import resolve
from app.pipeline import build_messages, _check_platform
from app.whitelist import FactPool
from connectors import ConnectorError, ModelScopeClient


FACTS = [
    {"id": "F99-01", "category": "便携", "value": "约 2.34 kg", "quote": "约 2.34 kg",
     "must_keep": ["约"], "caveat": "实际重量依配置而异。", "usage": "body", "section": "合成测试资料"},
    {"id": "F99-02", "category": "接口", "value": "HDMI × 1", "quote": "HDMI × 1",
     "must_keep": [], "caveat": "请用实际外设确认接口匹配。", "usage": "body", "section": "合成测试资料"},
]
TEST_NOTICE = ("隔离开发测试：以下 FACT_POOL 全部为合成夹具，绝非华为真实产品规格，也未经团队审批。"
               "本次仅测试输出结构和场景写作差异，不查询知识库，不可作为真实营销结果。"
               "请仍遵守系统 JSON 结构，article.lead 以【合成测试，不可发布】开头。")


def assess(output: dict) -> dict:
    article = output.get("article")
    strategy = output.get("strategy")
    if not isinstance(article, dict) or not isinstance(strategy, dict):
        return {"structure_ok": False, "reason": "article/strategy is not object"}
    parts = [article.get("title", ""), article.get("lead", ""), article.get("cta", "")]
    body = article.get("body")
    if not isinstance(body, list) or any(not isinstance(row, dict) or not isinstance(row.get("text"), str) for row in body):
        return {"structure_ok": False, "reason": "body is not text-object list"}
    parts += [row["text"] for row in body]
    text = "\n".join(p for p in parts if isinstance(p, str))
    used = set(re.findall(r"\[(F\d+-\d+)\]", text))
    allowed = {f["id"] for f in FACTS}
    hits = check_text(text, FACTS, platform="moments")
    platform_ok, platform_detail = _check_platform("moments", article, strategy)
    return {"structure_ok": True, "test_label_present": "合成测试" in text,
            "known_fact_ids_only": bool(used) and not (used - allowed),
            "compliance_hits": [asdict(h) for h in hits],
            "platform_ok": platform_ok, "platform_detail": platform_detail,
            "angle": strategy.get("angle"), "selected_points": strategy.get("selected_points")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("No API calls. Add --run for two isolated synthetic prompt tests.")
        return 0
    target = ROOT / "data/private/prompt-test"
    target.mkdir(parents=True, exist_ok=True)
    client = ModelScopeClient(timeout=60)
    report = {"checked_at": datetime.now().astimezone().isoformat(), "model": client.model,
              "input_kind": "synthetic_facts", "is_real_marketing_result": False,
              "ima_requests": 0, "cache_reads": 0, "runs": []}
    for scene, audience in (("school", "大学新生"), ("business", "经常出差的职场人")):
        it = resolve(product="MateBook D 14 2024", audience=audience, scene=scene, platform="moments",
                     variant="标准版", os_name="Windows")
        messages = build_messages(it, FactPool(allowed=FACTS, mode="test"), ImageResult(needed_min=1, needed_max=3), "")
        messages[1]["content"] = TEST_NOTICE + "\n\n" + messages[1]["content"]
        run = {"scene": scene, "mode": "test", "is_real_marketing_result": False}
        try:
            completion = client.chat(messages, max_tokens=2400, temperature=0.3)
            run.update(usage=completion.usage, request_id=completion.request_id, raw_output=completion.text)
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", completion.text.strip(), flags=re.I)
            out = json.loads(raw)
            if not isinstance(out, dict):
                raise ValueError("not object")
            run.update(output=out, assessment=assess(out))
        except ConnectorError as exc:
            run.update(error={"kind": exc.kind, "code": exc.code, "message": str(exc)})
        except (ValueError, TypeError, AttributeError):
            run.update(error={"kind": "invalid_model_structure"})
        report["runs"].append(run)
        (target / f"{scene}.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    report["stats"] = client.stats
    report["basic_checks_passed"] = all(r.get("assessment", {}).get("structure_ok") and
         r["assessment"].get("test_label_present") and r["assessment"].get("known_fact_ids_only") and
         r["assessment"].get("platform_ok") and not r["assessment"].get("compliance_hits") for r in report["runs"])
    (target / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": client.model, "basic_checks_passed": report["basic_checks_passed"],
                      "runs": [{"scene": r["scene"], "assessment": r.get("assessment"), "error": r.get("error")} for r in report["runs"]],
                      "is_real_marketing_result": False, "ima_requests": 0}, ensure_ascii=False, indent=2))
    return 0 if report["basic_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
