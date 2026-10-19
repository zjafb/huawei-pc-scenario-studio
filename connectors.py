"""Server-side, standard-library connectors. No approvals or synthetic fallbacks.

Credentials never belong in return values. Cache verification proves byte identity,
not human approval, remote freshness, product scope or image suitability.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ConnectorError(RuntimeError):
    def __init__(self, message: str, *, kind: str = "request_failed", code: Any = None,
                 provider_code: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.code = code
        self.provider_code = provider_code
        self.retry_after = retry_after


def _service_error(data: Any, status: int | None, secrets: tuple[str, ...],
                   retry_after: str | None = None) -> ConnectorError:
    """Separate recoverable throughput limits from exhausted account quotas."""
    message = _redact(_message(data, f"HTTP {status}" if status else "模型服务返回失败。"), secrets)
    detail = data.get("error") if isinstance(data, dict) else None
    detail = detail if isinstance(detail, dict) else data if isinstance(data, dict) else {}
    provider_code = _redact(str(detail.get("code") or detail.get("type") or ""), secrets)
    signal = (provider_code + " " + message).lower()
    if any(s in signal for s in ("free allocated quota", "budgetlimitexceeded", "arrearage",
                                 "billoverdue", "额度耗尽", "额度已用尽", "欠费", "daily limit", "daily quota")):
        kind = "quota"
    elif any(s in signal for s in ("allocationquota", "exceeded your current quota", "allocated quota exceeded",
                                   "token rate", "tokens per minute", "tokens per second")):
        kind = "token_rate_limit"
    elif "insufficient_quota" in signal:
        kind = "quota"
    elif status == 429 or any(s in signal for s in ("throttling", "rate limit", "rate_limit", "rate increased too quickly", "too many requests")):
        kind = "rate_limit"
    else:
        kind = "http_error" if status else "api_error"
    try:
        delay = float(retry_after) if retry_after is not None else None
        if delay is not None and (not 0 <= delay <= 120): delay = None
    except (ValueError, TypeError):
        delay = None
    return ConnectorError(message, kind=kind, code=status, provider_code=provider_code or None, retry_after=delay)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_open_request = build_opener(_NoRedirect()).open


def _setting(names: tuple[str, ...], file: Path) -> str:
    for name in names:
        if value := os.environ.get(name, "").strip():
            return value
    try:
        return file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value[:1200]


def _message(data: Any, default: str) -> str:
    if isinstance(data, dict):
        for name in ("error", "errors"):
            if isinstance(data.get(name), dict):
                return str(data[name].get("message") or data[name].get("msg") or default)
        return str(data.get("msg") or data.get("message") or default)
    return default


def _request_json(url: str, headers: dict[str, str], body: dict | None,
                  timeout: float, secrets: tuple[str, ...]) -> dict:
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(url, data=encoded, headers=headers, method="POST" if body is not None else "GET")
    try:
        with _open_request(req, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ConnectorError("接口响应过大。", kind="response_too_large")
        data = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(data, dict):
            raise ConnectorError("接口返回格式不符合预期。", kind="invalid_response")
        return data
    except HTTPError as exc:
        try:
            error = json.loads(exc.read(65536).decode("utf-8", errors="replace"))
        except (ValueError, UnicodeError):
            error = {}
        raise _service_error(error, exc.code, secrets,
                             exc.headers.get("Retry-After") if exc.headers else None) from None
    except (URLError, TimeoutError, OSError) as exc:
        raise ConnectorError(f"网络请求失败（{type(exc).__name__}）。", kind="network_error") from None
    except (ValueError, UnicodeError):
        raise ConnectorError("接口返回的 JSON 无法解析。", kind="invalid_response") from None


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: dict
    request_id: str | None
    finish_reason: str | None = None


class ModelScopeClient:
    BASE_URL = "https://api-inference.modelscope.cn/v1"

    def __init__(self, *, token: str | None = None, model: str | None = None,
                 timeout: float = 60):
        config = Path.home() / ".config" / "modelscope"
        self._token = token or _setting(("MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN"), config / "api_key")
        self.model = model or _setting(("MODELSCOPE_MODEL",), config / "model_id")
        self.timeout = timeout
        self.stats = {"model_requests": 0}
        self.last_completion: Completion | None = None
        if not self._token:
            raise ConnectorError("未配置魔搭访问令牌。", kind="missing_credentials")
        if not self.model:
            raise ConnectorError("未配置已验证的模型 ID。", kind="missing_model")

    def chat(self, messages: list[dict], *, max_tokens: int = 2048,
             temperature: float = 0.3, json_mode: bool = False) -> Completion:
        if not messages:
            raise ConnectorError("模型输入不能为空。", kind="invalid_input")
        self.stats["model_requests"] += 1
        payload={"model": self.model, "messages": messages, "max_tokens": max_tokens,
                 "temperature": temperature, "stream": False, "enable_thinking": False}
        if json_mode:payload['response_format']={'type':'json_object'}
        data = _request_json(
            self.BASE_URL + "/chat/completions",
            {"Authorization": "Bearer " + self._token, "Content-Type": "application/json"},
            payload,
            self.timeout, (self._token,),
        )
        if data.get("error") or (data.get("code") not in (None, 0, "0", 200, "200") and not data.get("choices")):
            raise _service_error(data, None, (self._token,))
        choices = data.get("choices") or []
        text = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(text, str) or not text.strip():
            raise ConnectorError("模型未返回正文；不能用固定结果代替。", kind="empty_completion")
        result = Completion(_redact(text, (self._token,)) if self._token in text else text,
                            self.model, data.get("usage") or {}, data.get("id"), choices[0].get("finish_reason"))
        self.last_completion = result
        return result

    def chat_json(self, messages: list[dict], **kwargs) -> dict:
        text = self.chat(messages, json_mode=True, **kwargs).text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except ValueError:
            raise ConnectorError("模型未返回合法 JSON。", kind="invalid_model_json") from None
        if not isinstance(data, dict):
            raise ConnectorError("模型 JSON 必须为对象。", kind="invalid_model_json")
        return data


@dataclass(frozen=True)
class MediaContent:
    data: bytes
    sha256: str
    content_type: str
    media_type: int


class IMAClient:
    BASE_URL = "https://ima.qq.com/openapi/wiki/v1/"

    def __init__(self, *, client_id: str | None = None, api_key: str | None = None,
                 timeout: float = 25, max_media_info_calls: int = 10):
        config = Path.home() / ".config" / "ima"
        self._client_id = client_id or _setting(("IMA_OPENAPI_CLIENTID", "IMA_CLIENT_ID"), config / "client_id")
        self._api_key = api_key or _setting(("IMA_OPENAPI_APIKEY", "IMA_API_KEY"), config / "api_key")
        self.timeout = timeout
        self.max_media_info_calls = max_media_info_calls
        self.stats = {"api_requests": 0, "media_info_requests": 0,
                      "text_downloads": 0, "image_downloads": 0}
        if not self._client_id or not self._api_key:
            raise ConnectorError("未配置 ima Client ID 或 API Key。", kind="missing_credentials")

    def _call(self, endpoint: str, body: dict) -> dict:
        self.stats["api_requests"] += 1
        result = _request_json(
            self.BASE_URL + endpoint,
            {"ima-openapi-clientid": self._client_id, "ima-openapi-apikey": self._api_key,
             "ima-openapi-ctx": "skill_version=1.1.10", "Content-Type": "application/json"},
            body, self.timeout, (self._client_id, self._api_key),
        )
        if result.get("code") != 0:
            message = _redact(_message(result, "ima 接口返回失败。"), (self._client_id, self._api_key))
            kind = "quota" if any(x in message.lower() for x in ("上限", "限额", "额度", "quota")) else "api_error"
            raise ConnectorError(message, kind=kind, code=result.get("code"))
        if not isinstance(result.get("data"), dict):
            raise ConnectorError("ima 返回的数据结构异常。", kind="invalid_response")
        return result["data"]

    def search_bases(self, name: str, *, cursor: str = "") -> dict:
        return self._call("search_knowledge_base", {"query": name, "cursor": cursor, "limit": 20})

    def find_base(self, name: str) -> dict:
        rows = self.search_bases(name).get("info_list") or []
        matches = [r for r in rows if r.get("kb_name", r.get("name")) == name]
        if len(matches) != 1:
            raise ConnectorError("指定知识库未找到或存在多个同名结果。", kind="needs_choice")
        row = matches[0]
        identifier = row.get("kb_id") or row.get("id")
        if not identifier:
            raise ConnectorError("知识库结果缺少标识。", kind="invalid_response")
        return {**row, "kb_id": identifier, "kb_name": name}

    def list_items(self, kb_id: str, *, folder_id: str | None = None,
                   cursor: str = "", limit: int = 50) -> dict:
        body = {"knowledge_base_id": kb_id, "cursor": cursor, "limit": min(max(limit, 1), 50)}
        if folder_id is not None:
            body["folder_id"] = folder_id
        return self._call("get_knowledge_list", body)

    def list_all(self, kb_id: str, *, folder_id: str | None = None, max_pages: int = 20) -> list:
        rows, cursor = [], ""
        for _ in range(max_pages):
            data = self.list_items(kb_id, folder_id=folder_id, cursor=cursor)
            rows.extend(data.get("knowledge_list") or [])
            if data.get("is_end") is True:
                return rows
            next_cursor = data.get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                raise ConnectorError("目录分页未前进，已停止。", kind="pagination_error")
            cursor = next_cursor
        raise ConnectorError("目录浏览达到本次页数上限。", kind="budget_exceeded")

    def list_path(self, kb_id: str, folder_titles: list[str]) -> list:
        """Resolve actual directory IDs from exact names; never invent IDs."""
        folder_id = None
        for title in folder_titles:
            rows = self.list_all(kb_id, folder_id=folder_id)
            matches = [r for r in rows if r.get("title") == title and r.get("media_type") == 99]
            if len(matches) != 1 or not matches[0].get("media_id"):
                raise ConnectorError("指定目录未找到或有多个同名目录，需明确选择。", kind="needs_choice")
            folder_id = matches[0]["media_id"]
        return self.list_all(kb_id, folder_id=folder_id)

    def search(self, kb_id: str, query: str, *, cursor: str = "") -> dict:
        return self._call("search_knowledge", {"knowledge_base_id": kb_id, "query": query, "cursor": cursor})

    def search_or_list(self, kb_id: str, query: str, *, folder_id: str | None = None) -> dict:
        rows = self.search(kb_id, query).get("info_list") or []
        if rows:
            return {"method": "search", "items": rows}
        return {"method": "directory_fallback", "items": self.list_all(kb_id, folder_id=folder_id)}

    def get_media_info(self, media_id: str) -> dict:
        if not media_id:
            raise ConnectorError("资料标识不能为空。", kind="invalid_input")
        if self.stats["media_info_requests"] >= self.max_media_info_calls:
            raise ConnectorError("达到本任务的资料请求预算。", kind="budget_exceeded")
        self.stats["media_info_requests"] += 1
        return self._call("get_media_info", {"media_id": media_id})

    def read_media(self, media_id: str, *, max_bytes: int = 15 * 1024 * 1024) -> MediaContent:
        info = self.get_media_info(media_id)
        if info.get("media_type") == 11:
            raise ConnectorError("该资料是笔记，需要 notes 原文读取接口。", kind="note_requires_reader")
        access = info.get("url_info") or {}
        url = access.get("url") or ""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ConnectorError("资料未提供有效 HTTPS 原文地址，请使用 ima 客户端查看。", kind="media_unavailable")
        # Forward only media-specific headers returned by ima, never IMA credentials.
        media_headers = dict(access.get("headers") or {})
        for name, value in media_headers.items():
            if name.lower() in ("ima-openapi-clientid", "ima-openapi-apikey") or value in (self._client_id, self._api_key):
                raise ConnectorError("媒体访问头含不应转发的 ima 凭证，已停止。", kind="unsafe_media_headers")
        try:
            with _open_request(Request(url, headers=media_headers), timeout=self.timeout) as response:
                raw = response.read(max_bytes + 1)
                content_type = response.headers.get("Content-Type", "application/octet-stream")
        except HTTPError as exc:
            raise ConnectorError(f"原文读取失败（HTTP {exc.code}），请使用 ima 客户端查看。", kind="media_unavailable", code=exc.code) from None
        except (URLError, OSError, TimeoutError):
            raise ConnectorError("原文读取失败，请使用 ima 客户端查看。", kind="media_unavailable") from None
        if len(raw) > max_bytes:
            raise ConnectorError("资料超过本次读取大小限制。", kind="response_too_large")
        media_type = int(info.get("media_type", 0))
        self.stats["image_downloads" if media_type == 9 else "text_downloads"] += 1
        return MediaContent(raw, hashlib.sha256(raw).hexdigest(), content_type, media_type)


@dataclass(frozen=True)
class CachedContent:
    data: bytes
    sha256: str
    mode: str = "cache"
    remote_freshness_verified: bool = False

    def text(self) -> str:
        return self.data.decode("utf-8-sig")


class VerifiedCache:
    """Reads original bytes; caller MUST separately enforce human approval/scope."""
    mode = "cache"
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()
        self.stats = {"cache_hits": 0}

    def read(self, filename: str, expected_sha256: str) -> CachedContent:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise ConnectorError("缓存缺少完整 SHA-256，不能放行。", kind="unverified_cache")
        path = (self.directory / filename).resolve()
        if not path.is_relative_to(self.directory):
            raise ConnectorError("缓存路径超出私有目录。", kind="unsafe_cache_path")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            raise ConnectorError("原始缓存文件缺失，不能用摘要代替。", kind="cache_missing") from None
        actual = hashlib.sha256(raw).hexdigest()
        if actual.lower() != expected_sha256.lower():
            raise ConnectorError("缓存指纹不匹配，需重新核对。", kind="cache_changed")
        self.stats["cache_hits"] += 1
        return CachedContent(raw, actual)


@dataclass(frozen=True)
class LiveContent:
    data: bytes
    sha256: str
    mode: str = "live"
    remote_freshness_verified: bool = True

    def text(self) -> str:
        return self.data.decode("utf-8-sig")


class LiveSourceReader:
    """One task only. Downloads from IMA, never reads historical disk cache.

    A second read within this same task reuses its just-downloaded bytes and is
    counted as live_reuses, not another download or a cache hit. Create a NEW
    reader for every task. Approval and image suitability remain caller checks.
    Any error latches this reader closed so later stages cannot retry or fall
    back. Source-map IDs must come from actual IMA directory/search results.
    """
    mode = "live"

    def __init__(self, ima: IMAClient, media_ids: dict[str, str]):
        self.ima = ima
        self.media_ids = dict(media_ids)
        self.contents: dict[str, LiveContent] = {}
        self.failure: ConnectorError | None = None
        self.live_reuses = 0

    @property
    def stats(self) -> dict:
        return {**self.ima.stats, "cache_hits": 0, "live_reuses": self.live_reuses,
                "verified_live_sources": len(self.contents)}

    def read(self, filename: str, expected_sha256: str) -> LiveContent:
        if self.failure is not None:
            raise self.failure
        try:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
                raise ConnectorError("来源缺少完整 SHA-256，需先核对来源。", kind="unverified_source")
            if filename in self.contents:
                source = self.contents[filename]
                self.live_reuses += 1
            else:
                media_id = self.media_ids.get(filename)
                if not media_id:
                    raise ConnectorError("未定位到本次任务的 ima 原始资料。", kind="source_not_mapped")
                media = self.ima.read_media(media_id)
                source = LiveContent(media.data, media.sha256)
            if source.sha256.lower() != expected_sha256.lower():
                raise ConnectorError("实时来源指纹与已核对版本不同，需重新核对。", kind="source_changed")
            self.contents[filename] = source
            return source
        except ConnectorError as exc:
            self.failure = exc
            raise
