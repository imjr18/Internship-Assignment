"""
Module: agent/tool_dispatcher.py

Routes tool calls through the MCP server via JSON-RPC 2.0 over HTTP.

Architecture:
    Agent (orchestrator.py)
      → dispatch_all() [this module]
        → MCP Server (localhost:8100/mcp, JSON-RPC)
          → Tool functions → Database

Falls back to direct dispatch if the MCP server is unreachable.
"""

from __future__ import annotations

import json
import os

import httpx
import structlog

logger = structlog.get_logger(__name__)

# MCP server URL — configurable via env var
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8100/mcp")

# Keep the tool registry for fallback and validation
VALID_TOOLS = {
    "search_restaurants",
    "check_availability",
    "create_reservation",
    "modify_reservation",
    "cancel_reservation",
    "get_guest_history",
    "add_to_waitlist",
    "escalate_to_human",
}

# Request counter for JSON-RPC IDs
_request_id = 0


def _next_id() -> int:
    global _request_id
    _request_id += 1
    return _request_id


async def _call_mcp(tool_name: str, arguments: dict, session_id: str) -> dict:
    """Call a tool via the MCP server's JSON-RPC endpoint.

    Returns:
        Standard tool response dict with success/data/error/error_code.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
            "_meta": {"session_id": session_id},
        },
    }

    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(MCP_SERVER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # Check for JSON-RPC error
    if "error" in data and data["error"] is not None:
        error_msg = data["error"].get("message", "MCP server error")
        logger.warning(
            "mcp_rpc_error",
            session_id=session_id,
            tool=tool_name,
            error=error_msg,
        )
        return {
            "success": False,
            "data": None,
            "error": error_msg,
            "error_code": "MCP_ERROR",
        }

    # Parse MCP result — content[0].text contains JSON tool result
    result_data = data.get("result", {})
    content_list = result_data.get("content", [])

    if content_list and content_list[0].get("type") == "text":
        return json.loads(content_list[0]["text"])

    # Fallback if content format is unexpected
    return {
        "success": False,
        "data": None,
        "error": "Unexpected MCP response format",
        "error_code": "MCP_ERROR",
    }


async def dispatch_tool_call(
    tool_name: str,
    arguments: dict,
    session_id: str,
) -> dict:
    """Execute a single tool call via the MCP server.

    Falls back to direct execution if MCP is unreachable.

    Args:
        tool_name: Function name (must be a valid tool).
        arguments: Parsed argument dict from LLM.
        session_id: For logging.

    Returns:
        Standard tool response dict with success/data/error/error_code.
    """
    # Hallucination detection
    if tool_name not in VALID_TOOLS:
        logger.warning(
            "hallucinated_tool_call",
            session_id=session_id,
            tool_name=tool_name,
        )
        return {
            "success": False,
            "data": None,
            "error": f"Unknown tool: {tool_name}. Valid tools: {', '.join(VALID_TOOLS)}",
            "error_code": "INVALID_INPUT",
        }

    logger.info(
        "dispatching_tool",
        session_id=session_id,
        tool=tool_name,
        arg_keys=list(arguments.keys()),
        via="mcp",
    )

    try:
        result = await _call_mcp(tool_name, arguments, session_id)
    except Exception as exc:
        logger.error(
            "mcp_dispatch_error",
            session_id=session_id,
            tool=tool_name,
            error=str(exc),
        )
        # Fall back to direct dispatch if MCP server is down
        logger.warning(
            "mcp_fallback_direct",
            session_id=session_id,
            tool=tool_name,
        )
        result = await _direct_dispatch(tool_name, arguments, session_id)

    logger.info(
        "tool_result",
        session_id=session_id,
        tool=tool_name,
        success=result.get("success"),
    )

    return result


async def _direct_dispatch(
    tool_name: str, arguments: dict, session_id: str
) -> dict:
    """Fallback: call tool function directly if MCP server is unreachable."""
    # Lazy import to avoid circular imports at module level
    from tools.recommendations import search_restaurants
    from tools.availability import check_availability
    from tools.reservations import (
        create_reservation,
        modify_reservation,
        cancel_reservation,
    )
    from tools.guest_profiles import get_guest_history
    from tools.waitlist import add_to_waitlist
    from tools.escalation import escalate_to_human

    registry = {
        "search_restaurants": search_restaurants,
        "check_availability": check_availability,
        "create_reservation": create_reservation,
        "modify_reservation": modify_reservation,
        "cancel_reservation": cancel_reservation,
        "get_guest_history": get_guest_history,
        "add_to_waitlist": add_to_waitlist,
        "escalate_to_human": escalate_to_human,
    }

    fn = registry.get(tool_name)
    if fn is None:
        return {
            "success": False,
            "data": None,
            "error": f"Unknown tool: {tool_name}",
            "error_code": "INVALID_INPUT",
        }

    try:
        return await fn(arguments)
    except Exception as exc:
        return {
            "success": False,
            "data": None,
            "error": str(exc),
            "error_code": "DB_ERROR",
        }


async def dispatch_all(
    tool_calls: list[dict],
    session_id: str,
) -> list[dict]:
    """Dispatch a list of tool calls sequentially via MCP.

    Args:
        tool_calls: List of {"id": str, "name": str, "arguments": dict}.
        session_id: For logging.

    Returns:
        List of {"tool_call_id": str, "result": dict, "content": str}.
        Each "content" is the JSON-serialised result for the LLM.
    """
    results = []
    for tc in tool_calls:
        result = await dispatch_tool_call(
            tool_name=tc["name"],
            arguments=tc["arguments"],
            session_id=session_id,
        )
        results.append(
            {
                "tool_call_id": tc["id"],
                "result": result,
                "content": json.dumps(result, default=str),
            }
        )
    return results
