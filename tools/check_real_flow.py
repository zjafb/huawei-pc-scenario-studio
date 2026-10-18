"""Explicit real model acceptance. Uses approved private source files, never synthetic facts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import run_task, to_text
from run_records import save_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Actually call the configured model using approved private evidence.")
    parser.add_argument("--case", choices=("all", "school-moments", "business-moments", "school-xhs"), default="all")
    args = parser.parse_args()
    if not args.run:
        print("No network call made. Use --run to execute real cache-mode model acceptance (uses model quota; no IMA calls).")
        return 0
    folder = ROOT / "data/private/acceptance" / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=False)
    base = dict(product="MateBook D 14 2024", variant="标准版", os_name="Windows", mode="cache")
    rows = []
    previous = None
    cases = [
        ("school-moments", dict(audience="大学新生", scene="开学季", platform="门店朋友圈")),
        ("business-moments", dict(audience="经常出差的职场人", scene="职场差旅", platform="门店朋友圈")),
        ("business-revision", dict(audience="经常出差的职场人", scene="职场差旅", platform="门店朋友圈",
                                    extra_request="换一个开头，以出发前整理会议资料的需求切入，保持一个已批准事实。")),
        ("school-xhs", dict(audience="大学新生", scene="开学季", platform="小红书")),
    ]
    if args.case != "all":
        cases = [case for case in cases if case[0] == args.case]
    for name, options in cases:
        if name == "business-revision":
            if previous is None:
                rows.append({"case": name, "executed": False, "reason": "Previous business draft was not safe to revise."})
                continue
            options["previous_article"] = previous
        rep = run_task(**base, **options)
        record = save_run(rep)
        (folder / (name + ".txt")).write_text(to_text(rep), encoding="utf-8-sig")
        rows.append({"case": name, "executed": True, "status": rep.status, "run_id": record.stem,
                     "source_stats": rep.run.get("source_stats", {}), "model_stats": rep.run.get("model_stats", {}),
                     "facts": [f["id"] for f in rep.used_facts], "images": [i["id"] for i in rep.images],
                     "checks": rep.checks, "revision_context_used": rep.run.get("revision_context_used", False)})
        print(json.dumps({"case": name, "status": rep.status, "run_id": record.stem}, ensure_ascii=False), flush=True)
        if name == "business-moments" and rep.status in ("qualified", "restricted"):
            previous = rep.article
    report = {"created_at": datetime.now().astimezone().isoformat(), "mode": "cache",
              "synthetic_test": False, "remote_freshness": "unverified", "cases": rows}
    (folder / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(folder / "summary.json")}, ensure_ascii=False))
    expected = {"school-moments": "qualified", "business-moments": "qualified", "business-revision": "qualified", "school-xhs": "restricted"}
    return 0 if len(rows) == len(cases) and all(row.get("status") == expected[row["case"]] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
