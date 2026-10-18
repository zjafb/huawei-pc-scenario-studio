"""图片选择规则测试。图片内容为测试用合成字节，仅用于测试。"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import images as im           # noqa: E402
from app.whitelist import Task         # noqa: E402
from connectors import VerifiedCache   # noqa: E402

BYTES_A, BYTES_B = b"fake-image-A", b"fake-image-B"


def img(iid, data, file, ok=True, model="D 14"):
    return {
        "id": iid, "name": iid, "file": file, "sha256": hashlib.sha256(data).hexdigest(),
        "scope": {"model": model, "year": 2024, "variants": ["标准版", "SE 版"], "os": ["Windows", "Linux"]},
        "approval": {"status": "approved", "checked_by": "SYNTHETIC-甲", "reviewed_by": "SYNTHETIC-乙", "date": "2026-10-18"} if ok
        else {"status": "pending", "checked_by": "", "reviewed_by": "", "date": ""},
    }


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._orig = im.IMAGES_FILE
        im.IMAGES_FILE = self.dir / "images.json"
        (self.dir / "a.png").write_bytes(BYTES_A)
        (self.dir / "b.png").write_bytes(BYTES_B)

    def tearDown(self):
        im.IMAGES_FILE = self._orig
        self.tmp.cleanup()

    def run_sel(self, images, platform, task=None):
        im.IMAGES_FILE.write_text(json.dumps({"images": images}, ensure_ascii=False), encoding="utf-8")
        return im.select_images(task or Task("D 14", variant="标准版", os="Windows"), platform, VerifiedCache(self.dir))

    def test_one_good_image_enough_for_moments(self):
        r = self.run_sel([img("A", BYTES_A, "a.png")], "moments")
        self.assertEqual(r.count, 1)
        self.assertTrue(r.enough)

    def test_one_image_not_enough_for_xhs_and_no_padding(self):
        r = self.run_sel([img("A", BYTES_A, "a.png")], "xhs")
        self.assertEqual(r.count, 1)
        self.assertFalse(r.enough)
        self.assertIn("需 3 张，仅有 1 张", r.shortage_text())

    def test_unapproved_image_not_selected(self):
        r = self.run_sel([img("A", BYTES_A, "a.png", ok=False)], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "not_approved")

    def test_missing_original_file_is_shortage_not_substituted(self):
        r = self.run_sel([img("A", BYTES_A, "nope.png")], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "file_missing")

    def test_changed_original_fails_fingerprint(self):
        (self.dir / "a.png").write_bytes(b"tampered")
        r = self.run_sel([img("A", BYTES_A, "a.png")], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "source_changed")

    def test_approval_pin_cannot_be_changed_with_manifest(self):
        row = img("A", BYTES_A, "a.png")
        row["approval"]["source_sha256"] = "0" * 64
        r = self.run_sel([row], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "source_changed")

    def test_same_reviewer_and_invalid_date_do_not_pass(self):
        for field, value in (("reviewed_by", "SYNTHETIC-甲"), ("date", "x")):
            row = img("A", BYTES_A, "a.png")
            row["approval"][field] = value
            r = self.run_sel([row], "moments")
            self.assertEqual(r.count, 0)
            self.assertEqual(r.decisions[0].kind, "not_approved")

    def test_other_model_image_never_borrowed(self):
        r = self.run_sel([img("X", BYTES_A, "a.png", model="D 16")], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "out_of_scope")

    def test_duplicate_content_not_counted_twice(self):
        r = self.run_sel([img("A", BYTES_A, "a.png"), img("A2", BYTES_A, "a.png")], "xhs")
        self.assertEqual(r.count, 1)

    def test_empty_scope_is_unknown_not_wildcard(self):
        i = img("A", BYTES_A, "a.png")
        i["scope"] = {"model": "D 14", "year": 2024, "variants": [], "os": []}
        r = self.run_sel([i], "moments")
        self.assertEqual(r.count, 0)
        self.assertEqual(r.decisions[0].kind, "out_of_scope")

    def test_appearance_only_image_allowed_for_any_variant(self):
        i = img("A", BYTES_A, "a.png")
        i["scope"] = {"model": "D 14", "year": 2024, "appearance_only": True, "variants": [], "os": []}
        for var in ("标准版", "SE 版"):
            r = self.run_sel([i], "moments", Task("D 14", variant=var, os="Linux"))
            self.assertEqual(r.count, 1)

    def test_appearance_only_still_rejected_for_other_model(self):
        i = img("A", BYTES_A, "a.png")
        i["scope"] = {"model": "D 14", "year": 2024, "appearance_only": True, "variants": [], "os": []}
        r = self.run_sel([i], "moments", Task("D 16"))
        self.assertEqual(r.count, 0)

    def test_real_images_file_has_no_unsigned_approval(self):
        if not self._orig.exists():
            self.skipTest("Private image approvals are not distributed with public source.")
        for i in json.loads(self._orig.read_text(encoding="utf-8"))["images"]:
            a = i["approval"]
            if a["status"] == "approved":
                self.assertTrue(a["checked_by"] and a["reviewed_by"], i["id"])


if __name__ == "__main__":
    unittest.main()
