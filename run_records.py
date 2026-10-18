"""Private application run records. Never a source cache or approval store."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _secrets() -> list[str]:
    values = [os.environ.get(k, "").strip() for k in ("MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN",
              "IMA_API_KEY", "IMA_OPENAPI_APIKEY", "IMA_CLIENT_ID", "IMA_OPENAPI_CLIENTID")]
    for service, key in (("ima", "api_key"), ("ima", "client_id"), ("modelscope", "api_key")):
        try:
            values.append((Path.home() / ".config" / service / key).read_text(encoding="utf-8").strip())
        except FileNotFoundError:
            pass
    return list({v for v in values if len(v) >= 8})


def _serializable(value):
    if isinstance(value, (bytes, bytearray)):
        return {"binary_omitted": True, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Path):
        return str(value)
    raise TypeError("Unsupported value in run record")


def save_run(report, *, directory: str | Path | None = None, secrets: list[str] | None = None) -> Path:
    """Save the actual supplied Report; caller must report any write failure.

    live, cache and test histories are separated. Tests do not become live results.
    Historical records must never be read to satisfy a new live source request.
    """
    payload = asdict(report) if is_dataclass(report) else dict(report)
    mode = payload.get("mode")
    if mode not in ("live", "cache", "test"):
        raise ValueError("Unknown run mode.")
    now = datetime.now().astimezone()
    identifier = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:12]
    result = {"run_id": identifier, "saved_at": now.isoformat(), "synthetic_test": mode == "test",
              "record_purpose": "execution_history_only; never current evidence or approval",
              "report": payload}
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=_serializable)
    for secret in (_secrets() if secrets is None else secrets):
        if secret:
            encoded = encoded.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
    folder = (Path(directory) if directory is not None else ROOT / "data/private/runs") / mode
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (identifier + ".json")
    with target.open("x", encoding="utf-8") as handle:
        handle.write(encoded)
    return target
