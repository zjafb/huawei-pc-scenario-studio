"""Synthetic transport tests. These are NOT real project running results."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from connectors import ConnectorError, IMAClient, ModelScopeClient, VerifiedCache


class Response(io.BytesIO):
    def __init__(self, data, content_type="application/json"):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode())
        self.headers = {"Content-Type": content_type}


def ok(data):
    return Response({"code": 0, "data": data})


class ConnectorTests(unittest.TestCase):
    @patch('connectors._request_json')
    def test_structured_generation_requests_provider_json_object_mode(self,request):
        request.return_value={'choices':[{'message':{'content':'{"ok":true}'}}]}
        result=ModelScopeClient(token='synthetic-token',model='synthetic-model').chat_json([{'role':'user','content':'JSON'}])
        self.assertEqual({'ok':True},result)
        self.assertEqual({'type':'json_object'},request.call_args.args[2]['response_format'])

    def ima(self, **kwargs):
        return IMAClient(client_id="synthetic-client", api_key="synthetic-key", **kwargs)

    def model(self):
        return ModelScopeClient(token="synthetic-model-token", model="synthetic/model")

    @patch("connectors._open_request")
    def test_model_completion_and_usage_are_not_fabricated(self, open_request):
        open_request.return_value = Response({"choices": [{"message": {"content": '{"ok":true}'}}], "usage": {"total_tokens": 42}, "id": "test-request"})
        client = self.model()
        result = client.chat([{"role": "user", "content": "test"}])
        self.assertEqual(result.usage, {"total_tokens": 42})
        self.assertEqual(result.request_id, "test-request")
        self.assertEqual(client.stats["model_requests"], 1)

    @patch("connectors._open_request")
    def test_empty_model_output_fails_without_fallback(self, open_request):
        open_request.return_value = Response({"choices": []})
        with self.assertRaises(ConnectorError) as error:
            self.model().chat([{"role": "user", "content": "test"}])
        self.assertEqual(error.exception.kind, "empty_completion")

    @patch("connectors._open_request")
    def test_http_error_redacts_credentials(self, open_request):
        body = io.BytesIO(b'{"error":{"message":"bad synthetic-model-token"}}')
        open_request.side_effect = HTTPError("https://example.invalid", 403, "Forbidden", {}, body)
        with self.assertRaises(ConnectorError) as error:
            self.model().chat([{"role": "user", "content": "test"}])
        self.assertNotIn("synthetic-model-token", str(error.exception))
        self.assertEqual(error.exception.code, 403)

    @patch("connectors._open_request")
    def test_base_lookup_accepts_real_field_names(self, open_request):
        open_request.return_value = ok({"info_list": [{"kb_name": "target", "kb_id": "test-base"}]})
        self.assertEqual(self.ima().find_base("target")["kb_id"], "test-base")

    @patch("connectors._open_request")
    def test_empty_search_falls_back_to_directory(self, open_request):
        open_request.side_effect = [ok({"info_list": []}), ok({"knowledge_list": [{"title": "file"}], "is_end": True})]
        result = self.ima().search_or_list("test-base", "missing")
        self.assertEqual(result["method"], "directory_fallback")
        self.assertEqual(result["items"][0]["title"], "file")

    @patch("connectors._open_request")
    def test_directory_pagination_and_unchanged_cursor(self, open_request):
        open_request.side_effect = [ok({"knowledge_list": [1], "is_end": False, "next_cursor": "next"}), ok({"knowledge_list": [2], "is_end": True})]
        self.assertEqual(self.ima().list_all("test-base"), [1, 2])
        open_request.side_effect = [ok({"knowledge_list": [], "is_end": False, "next_cursor": ""})]
        with self.assertRaises(ConnectorError) as error:
            self.ima().list_all("test-base")
        self.assertEqual(error.exception.kind, "pagination_error")

    @patch("connectors._open_request")
    def test_quota_error_stops_without_retry(self, open_request):
        open_request.return_value = Response({"code": 1, "msg": "资料获取次数已达上限，请明天再尝试"})
        client = self.ima()
        with self.assertRaises(ConnectorError) as error:
            client.get_media_info("test-media")
        self.assertEqual(error.exception.kind, "quota")
        self.assertEqual(open_request.call_count, 1)

    @patch("connectors._open_request")
    def test_media_budget_is_checked_before_request(self, open_request):
        with self.assertRaises(ConnectorError) as error:
            self.ima(max_media_info_calls=0).get_media_info("test-media")
        self.assertEqual(error.exception.kind, "budget_exceeded")
        open_request.assert_not_called()

    @patch("connectors._open_request")
    def test_media_get_does_not_forward_ima_credentials(self, open_request):
        open_request.side_effect = [ok({"media_type": 7, "url_info": {"url": "https://media.example.invalid/test.md", "headers": {"X-Media-Ticket": "synthetic-ticket"}}}), Response(b"source text", "text/markdown")]
        result = self.ima().read_media("test-media")
        req = open_request.call_args_list[1].args[0]
        self.assertNotIn("ima-openapi-apikey", {key.lower() for key in req.headers})
        self.assertNotIn("synthetic-key", req.headers.values())
        self.assertEqual(result.sha256, hashlib.sha256(b"source text").hexdigest())

    @patch("connectors._open_request")
    def test_unavailable_and_unsafe_media_are_not_fetched(self, open_request):
        for url in ("", "http://media.example.invalid/test", "https://user:pass@media.example.invalid/test"):
            open_request.reset_mock()
            open_request.return_value = ok({"media_type": 9, "url_info": {"url": url}})
            with self.assertRaises(ConnectorError):
                self.ima().read_media("test-media")
            self.assertEqual(open_request.call_count, 1)

    def test_cache_hash_and_path_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "source.md").write_bytes(b"verified bytes")
            cache = VerifiedCache(folder)
            expected = hashlib.sha256(b"verified bytes").hexdigest()
            entry = cache.read("source.md", expected)
            self.assertEqual(entry.text(), "verified bytes")
            self.assertFalse(entry.remote_freshness_verified)
            for name, digest, kind in [("source.md", "0" * 64, "cache_changed"), ("../outside.md", expected, "unsafe_cache_path"), ("missing.md", expected, "cache_missing")]:
                with self.assertRaises(ConnectorError) as error:
                    cache.read(name, digest)
                self.assertEqual(error.exception.kind, kind)


if __name__ == "__main__":
    unittest.main()
