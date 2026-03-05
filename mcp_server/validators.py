"""
Module: mcp_server/validators.py
Responsibility: Pydantic models for MCP JSON-RPC requests/responses and
input validation utilities.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field
import structlog

from mcp_server.tool_schemas import MCP_TOOLS_SCHEMA_LIST

logger = structlog.get_logger(__name__)


# ── JSON-RPC 2.0 Models ────────────────────────────────────────

class JsonRpcRequest(BaseModel):
    """Incoming JSON-RPC 2.0 request."""
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcResponse(BaseModel):
    """Outgoing JSON-RPC 2.0 response."""
    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict[str, Any] | None = None


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""
    code: int
    message: str
    data: Any = None


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def make_error_response(
    req_id: int | str | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict:
    """Build a JSON-RPC error response dict."""
    resp = {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        resp["error"]["data"] = data
    return resp


def make_success_response(
    req_id: int | str | None,
    result: Any,
) -> dict:
    """Build a JSON-RPC success response dict."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": result,
    }


# ── Tool Input Validation ──────────────────────────────────────

# Build a lookup of tool name → required fields for fast validation
_TOOL_REQUIRED: dict[str, list[str]] = {}
_TOOL_NAMES: set[str] = set()

for _schema in MCP_TOOLS_SCHEMA_LIST:
    name = _schema["name"]
    _TOOL_NAMES.add(name)
    _TOOL_REQUIRED[name] = _schema["inputSchema"].get("required", [])


def validate_tool_input(tool_name: str, payload: dict) -> tuple[bool, str]:
    """Validate that a tool call has the correct name and required params.

    Returns:
        (is_valid, error_message) — error_message is empty if valid.
    """
    if tool_name not in _TOOL_NAMES:
        return False, f"Unknown tool: {tool_name}. Valid: {', '.join(sorted(_TOOL_NAMES))}"

    required = _TOOL_REQUIRED.get(tool_name, [])
    missing = [r for r in required if r not in payload or payload[r] is None]
    if missing:
        return False, f"Missing required parameters: {', '.join(missing)}"

    return True, ""


# ── Rate Limiting ──────────────────────────────────────────────

# Simple in-memory token-bucket rate limiter
_RATE_LIMIT: dict[str, list[float]] = defaultdict(list)
_MAX_REQUESTS_PER_MINUTE = 200
_WINDOW_SECONDS = 60


def check_rate_limit(session_id: str) -> bool:
    """Return True if the session is within rate limits.

    Uses a sliding-window counter: max 60 requests per 60 seconds.
    """
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    # Prune old entries
    _RATE_LIMIT[session_id] = [
        t for t in _RATE_LIMIT[session_id] if t > window_start
    ]

    if len(_RATE_LIMIT[session_id]) >= _MAX_REQUESTS_PER_MINUTE:
        logger.warning(
            "rate_limit_exceeded",
            session_id=session_id,
            count=len(_RATE_LIMIT[session_id]),
        )
        return False

    _RATE_LIMIT[session_id].append(now)
    return True
