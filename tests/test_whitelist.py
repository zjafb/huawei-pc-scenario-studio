"""白名单规则测试（V2-01）。使用临时目录里的合成数据，仅用于测试，不是真实运行结果。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import whitelist as wl            # noqa: E402
from connectors import VerifiedCache       # noqa: E402

SRC_TEXT = "测试用原文：重量 约 1.39 kg。色域 100% sRGB。\n"
SRC_SHA = hashlib.sha256(SRC_TEXT.encode("utf-8")).hexdigest()


def approved(extra=None):
    d = {"status": "approved", "checked_by": "甲", "reviewed_by": "乙", "date": "2026-10-18"}
    d.update(extra or {})
    return d


def make_fact(fid, variants, os_list=("Windows", "Linux"), status_ok=True):
    return {
        "id": fid, "attr": "weight", "category": "便携", "value": "约 1.39 kg", "quote": "约 1.39 kg",
        "scope": {"model": "D 14", "year": 2024, "variants": variants, "os": list(os_list)},
        "source": "S", "section": "s", "usage": "body",
        "approval": approved() if status_ok else {"status": "pending", "checked_by": "", "reviewed_by": "", "date": ""},
    }


class WhitelistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "S.md").write_bytes(SRC_TEXT.encode("utf-8"))
        self._orig = wl.WHITELIST_FILE
        wl.WHITELIST_FILE = self.dir / "facts.json"

    def tearDown(self):
        wl.WHITELIST_FILE = self._orig
        self.tmp.cleanup()

    def write(self, facts, sha=SRC_SHA):
        wl.WHITELIST_FILE.write_text(json.dumps({
            "_来源": {"S": {"file": "S.md", "sha256": sha, "title": "测试来源"}},
            "facts": facts}, ensure_ascii=False), encoding="utf-8")

    def pool(self, task):
        return wl.build_fact_pool(task, VerifiedCache(self.dir))

    def ids(self, pool):
        return {f["id"] for f in pool.allowed}

    def test_unapproved_fact_never_allowed(self):
        self.write([make_fact("A", ["标准版", "SE 版"], status_ok=False)])
        p = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "not_approved")

    def test_missing_reviewer_not_allowed(self):
        f = make_fact("A", ["标准版", "SE 版"])
        f["approval"]["reviewed_by"] = ""
        self.write([f])
        p = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p), set())

    def test_switch_to_d16_excludes_only_for_this_task_then_back_ok(self):
        self.write([make_fact("A", ["标准版", "SE 版"])])
        p16 = self.pool(wl.Task("D 16", variant=None, os="Windows"))
        self.assertEqual(self.ids(p16), set())
        self.assertEqual(p16.decisions[0].kind, "out_of_scope")
        # 切回 D 14：原批准仍有效（批准状态没有被改动）
        p14 = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p14), {"A"})
        self.assertEqual(wl.load_raw()["facts"][0]["approval"]["status"], "approved")

    def test_changed_source_fingerprint_invalidates(self):
        self.write([make_fact("A", ["标准版", "SE 版"])], sha="0" * 64)
        p = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "source_changed")

    def test_source_file_tampered_invalidates(self):
        self.write([make_fact("A", ["标准版", "SE 版"])])
        (self.dir / "S.md").write_bytes((SRC_TEXT + "被改动").encode("utf-8"))
        p = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "source_changed")

    def test_shared_fact_usable_for_both_variants(self):
        self.write([make_fact("shared", ["标准版", "SE 版"])])
        self.assertEqual(self.ids(self.pool(wl.Task("D 14", variant="标准版", os="Windows"))), {"shared"})
        self.assertEqual(self.ids(self.pool(wl.Task("D 14", variant="SE 版", os="Windows"))), {"shared"})

    def test_standard_only_fact_not_usable_for_se(self):
        self.write([make_fact("std", ["标准版"])])
        self.assertEqual(self.ids(self.pool(wl.Task("D 14", variant="标准版", os="Windows"))), {"std"})
        p = self.pool(wl.Task("D 14", variant="SE 版", os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "out_of_scope")

    def test_version_unknown_blocks_version_dependent_fact(self):
        self.write([make_fact("std", ["标准版"])])
        p = self.pool(wl.Task("D 14", variant=None, os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "scope_unknown")

    def test_windows_only_fact_not_for_linux(self):
        self.write([make_fact("win", ["标准版", "SE 版"], os_list=("Windows",))])
        self.assertEqual(self.ids(self.pool(wl.Task("D 14", variant="标准版", os="Windows"))), {"win"})
        p = self.pool(wl.Task("D 14", variant="标准版", os="Linux"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "out_of_scope")

    def test_windows_only_fact_blocked_when_os_unknown(self):
        self.write([make_fact("win", ["标准版", "SE 版"], os_list=("Windows",))])
        p = self.pool(wl.Task("D 14", variant="标准版", os=None))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "scope_unknown")

    def test_empty_scope_is_unknown_not_wildcard(self):
        f = make_fact("x", ["标准版"])
        f["scope"] = {}
        self.write([f])
        p = self.pool(wl.Task("D 14", variant="标准版", os="Windows"))
        self.assertEqual(self.ids(p), set())
        self.assertEqual(p.decisions[0].kind, "scope_unknown")


class RealWhitelistTests(unittest.TestCase):
    def test_real_whitelist_has_no_unsigned_approval(self):
        """真实白名单里，任何标为 approved 的条目都必须有两人签字（防止 AI 或手误代签）。"""
        if not wl.WHITELIST_FILE.exists():
            self.skipTest("Private real approvals are not distributed with public source.")
        for f in wl.load_raw()["facts"]:
            a = f["approval"]
            if a["status"] == "approved":
                self.assertTrue(a["checked_by"] and a["reviewed_by"], f["id"])


if __name__ == "__main__":
    unittest.main()
