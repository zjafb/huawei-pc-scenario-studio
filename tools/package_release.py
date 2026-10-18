"""Build a public source archive from an explicit allowlist, excluding all private evidence."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from check_release import configured_secrets, inspect_file

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "requirements.txt", "app.py", "run.py", "run_records.py", "connectors.py",
         "Dockerfile", ".dockerignore", ".gitignore", ".env.example",
         "docs/deployment.md", "docs/acceptance.md"]
PATTERNS = ["app/*.py", "app/assets/*.css", "app/assets/*.js", "app/assets/fonts/*", "rules/*.md", "prompts/*.md", "tests/test_*.py",
            "examples/whitelist/*.json", "tools/*.py", "tools/*.ps1"]


def main():
    names = sorted(set(FILES + [p.relative_to(ROOT).as_posix() for pattern in PATTERNS for p in ROOT.glob(pattern)]))
    candidates = [(name, (ROOT / name).read_bytes()) for name in names]
    secrets = configured_secrets()
    findings = [f for name, content in candidates for f in inspect_file(name, content, secrets)]
    if findings:
        print(json.dumps({"passed": False, "findings": findings}, ensure_ascii=False, indent=2))
        return 1
    release_root = ROOT / "data/private/release"
    release_root.mkdir(parents=True, exist_ok=True)
    name = "public-source-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]
    destination = release_root / name
    destination.mkdir()
    manifest = {"created_at": datetime.now().astimezone().isoformat(),
                "purpose": "public source only; excludes real knowledge, approvals, credentials and run outputs",
                "configured_credentials_scanned": bool(secrets),
                "files": [{"path": p, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} for p, raw in candidates]}
    for path, raw in candidates:
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    manifest_raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    (destination / "release-manifest.json").write_bytes(manifest_raw)
    archive = release_root / (name + ".zip")
    with ZipFile(archive, "x", ZIP_DEFLATED) as bundle:
        for path, raw in candidates:
            bundle.writestr(path, raw)
        bundle.writestr("release-manifest.json", manifest_raw)
    print(json.dumps({"passed": True, "files": len(candidates), "folder": str(destination),
                      "archive": str(archive), "remote_history_scanned": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
