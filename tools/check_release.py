"""Check explicit publish candidates without printing secret values.

Default: read the Git index (including staged file bytes). No Git index means
unverified, not a passing release. --files checks only the specified files.
This does not check remote Git history or authorize publishing source material.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent


def private_path(name: str) -> bool:
    p = PurePosixPath(name.replace("\\", "/"))
    parts = tuple(x.lower() for x in p.parts)
    if any(x in {".venv", "__pycache__", ".config"} for x in parts):
        return True
    if parts[:2] in {("data", "private"), ("tools", "ima-official")}:
        return True
    if parts and (parts[0] in {"tmp", "outputs"} or parts[0].startswith("华为pc全板块深度知识库")):
        return True
    return p.name.lower().startswith(".env") and p.name != ".env.example"


def configured_secrets() -> list[str]:
    values = []
    for name in ("MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN", "IMA_API_KEY", "IMA_OPENAPI_APIKEY",
                 "IMA_CLIENT_ID", "IMA_OPENAPI_CLIENTID"):
        if val := os.environ.get(name, "").strip():
            values.append(val)
    for service, field in (("ima", "client_id"), ("ima", "api_key"), ("modelscope", "api_key")):
        try:
            values.append((Path.home() / ".config" / service / field).read_text(encoding="utf-8").strip())
        except FileNotFoundError:
            pass
    return list({x for x in values if len(x) >= 8})


def inspect_file(name: str, content: bytes, secrets: list[str]) -> list[dict]:
    findings = []
    if private_path(name):
        findings.append({"file": name, "reason": "private_or_runtime_file"})
    if any(value.encode(enc) in content for value in secrets for enc in ("utf-8", "utf-16-le", "utf-16-be")):
        findings.append({"file": name, "reason": "configured_credential_present"})
    # Real knowledge quotations need a separate permission decision; templates
    # with empty facts may be public. Do not print any source quotation.
    if name.replace("\\", "/").startswith("data/whitelist/") and name.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8-sig"))
            entries = data.get("facts", []) + data.get("images", [])
            if data.get("_来源") or entries:
                findings.append({"file": name, "reason": "knowledge_source_material_requires_review"})
        except (ValueError, UnicodeError, AttributeError, TypeError):
            findings.append({"file": name, "reason": "whitelist_unreadable"})
    return findings


def git_index(root: Path) -> list[tuple[str, bytes]]:
    listed = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=True)
    result = []
    for entry in listed.stdout.split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, oid, stage = meta.split()
        name = path.decode("utf-8", errors="replace")
        if stage != b"0" or mode == b"160000":
            raise ValueError("Unmerged paths or submodules need separate release review.")
        blob = subprocess.run(["git", "cat-file", "blob", oid.decode("ascii")], cwd=root,
                              capture_output=True, check=True)
        result.append((name, blob.stdout))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", help="Explicit project-relative candidates; not the Git index.")
    args = parser.parse_args()
    try:
        if args.files:
            candidates = []
            for name in args.files:
                file = (ROOT / name).resolve()
                if not file.is_relative_to(ROOT):
                    raise ValueError("Candidate is outside project directory.")
                candidates.append((file.relative_to(ROOT).as_posix(), file.read_bytes()))
            scope = "explicit_files_only"
        else:
            candidates = git_index(ROOT)
            scope = "git_index_only"
    except (OSError, subprocess.CalledProcessError, ValueError):
        print(json.dumps({"passed": False, "verified": False,
                          "reason": "Cannot read requested release candidates; no passing claim."}))
        return 2
    secrets = configured_secrets()
    findings = [hit for name, raw in candidates for hit in inspect_file(name, raw, secrets)]
    result = {"passed": bool(candidates) and not findings, "scope": scope,
              "files_checked": len(candidates), "configured_secrets_available": bool(secrets),
              "findings": findings,
              "limits": "No remote history scan; no general permission-to-publish determination."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
