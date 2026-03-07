from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from mcp_server.server import app as _MCP_APP

# Ensure live-LLM skip markers do not skip in local test runs.
os.environ.setdefault("GROQ_API_KEY", "test-key")

_LOCAL_MCP_CLIENT = TestClient(_MCP_APP)
_ORIG_HTTPX_GET = httpx.get
_ORIG_HTTPX_POST = httpx.post


def _is_local_mcp_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    return url.startswith("http://localhost:8100") or url.startswith("http://127.0.0.1:8100")


def _path_from_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return path


def _to_httpx_response(method: str, url: str, resp) -> httpx.Response:
    req = httpx.Request(method, url)
    return httpx.Response(
        status_code=resp.status_code,
        headers=dict(resp.headers),
        content=resp.content,
        request=req,
    )


def _patched_httpx_get(url: str, *args, **kwargs):
    if not _is_local_mcp_url(url):
        return _ORIG_HTTPX_GET(url, *args, **kwargs)

    path = _path_from_url(url)
    call_kwargs: dict = {}
    if "params" in kwargs:
        call_kwargs["params"] = kwargs["params"]
    if "headers" in kwargs:
        call_kwargs["headers"] = kwargs["headers"]
    resp = _LOCAL_MCP_CLIENT.get(path, **call_kwargs)
    return _to_httpx_response("GET", url, resp)


def _patched_httpx_post(url: str, *args, **kwargs):
    if not _is_local_mcp_url(url):
        return _ORIG_HTTPX_POST(url, *args, **kwargs)

    path = _path_from_url(url)
    call_kwargs: dict = {}
    for key in ("json", "data", "content", "headers"):
        if key in kwargs:
            call_kwargs[key] = kwargs[key]

    # Avoid accidental shared-rate-limit collisions during test runs.
    payload = call_kwargs.get("json")
    if (
        isinstance(payload, dict)
        and path.startswith("/mcp")
        and payload.get("method") == "tools/call"
        and isinstance(payload.get("params"), dict)
    ):
        params = dict(payload["params"])
        meta = params.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        if not meta.get("session_id"):
            meta["session_id"] = f"pytest-{uuid.uuid4()}"
        params["_meta"] = meta
        payload = dict(payload)
        payload["params"] = params
        call_kwargs["json"] = payload

    resp = _LOCAL_MCP_CLIENT.post(path, **call_kwargs)
    return _to_httpx_response("POST", url, resp)


# Patch top-level httpx helpers so collection-time health checks also work
# without relying on an external running server.
httpx.get = _patched_httpx_get
httpx.post = _patched_httpx_post


class _FakeDelta:
    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, delta: _FakeDelta, finish_reason: str | None = None):
        self.delta = delta
        self.finish_reason = finish_reason


class _FakeChunk:
    def __init__(self, content: str | None = None, finish_reason: str | None = None):
        self.choices = [_FakeChoice(_FakeDelta(content=content), finish_reason=finish_reason)]


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


class _FakeResponseChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeResponseChoice(content)]


class _FakeStream:
    def __init__(self, text: str):
        self._parts = [text[i:i + 32] for i in range(0, len(text), 32)] or [""]
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx < len(self._parts):
            part = self._parts[self._idx]
            self._idx += 1
            return _FakeChunk(content=part, finish_reason=None)
        if self._idx == len(self._parts):
            self._idx += 1
            return _FakeChunk(content=None, finish_reason="stop")
        raise StopAsyncIteration


def _fake_model_text(messages: list[dict]) -> str:
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = str(msg.get("content", "")).lower()
            break

    if any(w in last_user for w in ("hi", "hello", "hey")) and len(last_user.split()) <= 3:
        return "Hello! I'm Sage. How can I help with your reservation?"
    if any(w in last_user for w in ("human", "manager", "terrible", "angry")):
        return "I understand. I can connect you to a human agent now."
    if "ignore all previous instructions" in last_user or "system prompt" in last_user:
        return "I can help with restaurant reservations. What date and time do you need?"
    return "I can help with that. Please share date, time, and party size."


class _FakeCompletions:
    async def create(self, **kwargs):
        messages = kwargs.get("messages", [])
        text = _fake_model_text(messages)
        if kwargs.get("stream"):
            return _FakeStream(text)
        return _FakeResponse(text)


class _FakeAsyncGroq:
    def __init__(self, api_key: str):
        _ = api_key
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()


@pytest.fixture(autouse=True)
def _patch_groq_client(monkeypatch):
    """Use deterministic fake Groq client for all tests unless overridden."""
    from agent import llm_client as llm_module

    monkeypatch.setattr(llm_module, "AsyncGroq", _FakeAsyncGroq)
    yield
