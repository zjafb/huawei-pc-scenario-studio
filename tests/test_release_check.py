"""Synthetic release-scan cases. Never use actual keys in these fixtures."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("release_check", Path(__file__).resolve().parents[1] / "tools/check_release.py")
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


class ReleaseCheckTests(unittest.TestCase):
    def test_private_paths_and_env_template(self):
        for name in ("data/private/A14.md", "tmp/test.txt", "outputs/result.json", ".env", ".env.local", ".venv/x"):
            self.assertTrue(release_check.private_path(name), name)
        self.assertFalse(release_check.private_path(".env.example"))
        self.assertFalse(release_check.private_path("connectors.py"))

    def test_credential_not_returned_in_findings(self):
        secret = "SYNTHETIC-RELEASE-KEY-1234567890"
        hits = release_check.inspect_file("app.py", secret.encode(), [secret])
        self.assertTrue(hits)
        self.assertNotIn(secret, str(hits))
        self.assertEqual("configured_credential_present", hits[0]["reason"])

    def test_utf16_secret_detected(self):
        secret = "SYNTHETIC-UTF16-KEY-1234567890"
        self.assertTrue(release_check.inspect_file("report.txt", secret.encode("utf-16-le"), [secret]))

    def test_real_source_whitelist_needs_review_but_empty_template_allowed(self):
        self.assertTrue(release_check.inspect_file("data/whitelist/facts.json", b'{"facts":[{"quote":"synthetic quote"}]}', []))
        self.assertFalse(release_check.inspect_file("data/whitelist/template.json", b'{"facts":[]}', []))


if __name__ == "__main__":
    unittest.main()
