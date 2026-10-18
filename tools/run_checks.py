"""Run automatic checks with real connector networking forbidden.

Exit 0 only when all tests pass. Synthetic tests are never marketing results.
Detailed output stays in data/private/test-status.json and test-details.txt.
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    output = io.StringIO()
    with patch("connectors._open_request", side_effect=AssertionError("Network forbidden in automatic checks")):
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    report = {"checked_at": datetime.now().astimezone().isoformat(), "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful(),
              "network_guard": True, "failed_tests": [str(t) for t, _ in result.failures],
              "errored_tests": [str(t) for t, _ in result.errors],
              "skipped": [{"test": str(t), "reason": reason} for t, reason in result.skipped],
              "test_inputs": "synthetic; not marketing results"}
    target = ROOT / "data/private"
    target.mkdir(parents=True, exist_ok=True)
    (target / "test-status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "test-details.txt").write_text(output.getvalue(), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
