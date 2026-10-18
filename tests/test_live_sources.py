"""Live-source control flow uses synthetic mocked responses, no network."""
import hashlib
import unittest
from unittest.mock import patch

from connectors import ConnectorError, IMAClient, LiveSourceReader, MediaContent


class LiveSourceTests(unittest.TestCase):
    def setUp(self):
        self.ima = IMAClient(client_id="SYNTHETIC-ID", api_key="SYNTHETIC-KEY")
        self.raw = b"synthetic source"
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.media = MediaContent(self.raw, self.sha, "text/markdown", 7)

    def test_download_is_live_and_same_task_reuse_is_distinguished(self):
        reader = LiveSourceReader(self.ima, {"source.md": "SYNTHETIC-MEDIA"})
        with patch.object(self.ima, "read_media", return_value=self.media) as read:
            source = reader.read("source.md", self.sha)
            self.assertEqual("live", source.mode)
            self.assertTrue(source.remote_freshness_verified)
            self.assertEqual(self.raw.decode(), source.text())
            reader.read("source.md", self.sha)
            read.assert_called_once_with("SYNTHETIC-MEDIA")
        self.assertEqual(1, reader.stats["live_reuses"])
        self.assertEqual(0, reader.stats["cache_hits"])

    def test_new_task_requires_new_download(self):
        with patch.object(self.ima, "read_media", return_value=self.media) as read:
            for _ in range(2):
                LiveSourceReader(self.ima, {"source.md": "SYNTHETIC-MEDIA"}).read("source.md", self.sha)
            self.assertEqual(2, read.call_count)

    def test_quota_latches_closed_without_retry_or_disk_fallback(self):
        reader = LiveSourceReader(self.ima, {"source.md": "SYNTHETIC-MEDIA", "image.png": "SYNTHETIC-IMAGE"})
        error = ConnectorError("synthetic quota", kind="quota", code=220021)
        with patch.object(self.ima, "read_media", side_effect=error) as read:
            for filename in ("source.md", "image.png", "source.md"):
                with self.assertRaises(ConnectorError) as raised:
                    reader.read(filename, self.sha)
                self.assertEqual("quota", raised.exception.kind)
            self.assertEqual(1, read.call_count)
        self.assertEqual({}, reader.contents)

    def test_changed_remote_source_not_approved(self):
        reader = LiveSourceReader(self.ima, {"source.md": "SYNTHETIC-MEDIA"})
        with patch.object(self.ima, "read_media", return_value=self.media):
            with self.assertRaises(ConnectorError) as raised:
                reader.read("source.md", "0" * 64)
        self.assertEqual("source_changed", raised.exception.kind)
        self.assertFalse(reader.contents)

    def test_unmapped_source_never_reads_disk_or_api(self):
        with patch.object(self.ima, "read_media") as read:
            with self.assertRaises(ConnectorError):
                LiveSourceReader(self.ima, {}).read("source.md", self.sha)
            read.assert_not_called()

    def test_folder_path_uses_returned_ids_unchanged(self):
        rows = [[{"title": "root", "media_id": "folder_123", "media_type": 99}],
                [{"title": "product", "media_id": "folder_456", "media_type": 99}],
                [{"title": "synthetic.md", "media_id": "synthetic-media", "media_type": 7}]]
        with patch.object(self.ima, "list_all", side_effect=rows) as listing:
            output = self.ima.list_path("synthetic-kb", ["root", "product"])
        self.assertEqual("synthetic.md", output[0]["title"])
        self.assertEqual("folder_123", listing.call_args_list[1].kwargs["folder_id"])
        self.assertEqual("folder_456", listing.call_args_list[2].kwargs["folder_id"])


if __name__ == "__main__":
    unittest.main()
