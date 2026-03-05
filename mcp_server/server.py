"""
Module: mcp_server/server.py

FastAPI-based MCP (Model Context Protocol) server exposing GoodFoods tools
via JSON-RPC 2.0 over HTTP.

Endpoints:
    POST /mcp — JSON-RPC 2.0 dispatch for:
        - initialize:   Server handshake, returns capabilities
        - tools/list:   Returns all available tool schemas
        - tools/call:   Dispatches a tool call with validation

    GET /health — Health check endpoint

Usage:
    uvicorn mcp_server.server:app --port 8100
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog

from database.seed_data import run_seed
from agent.tool_dispatcher import dispatch_tool_call
from mcp_server.tool_schemas import MCP_TOOLS_SCHEMA_LIST
from mcp_server.validators import (
    JsonRpcRequest,
    make_error_response,
    make_success_response,
    validate_tool_input,
    check_rate_limit,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)

logger = structlog.get_logger(__name__)

# ── MCP Server Metadata ────────────────────────────────────────

SERVER_INFO = {
    "name": "goodfoods-mcp-server",
    "version": "1.0.0",
    "description": (
        "MCP server for GoodFoods restaurant reservation system. "
        "Exposes 8 tools: search, availability, reservations, "
        "waitlist, guest history, and escalation."
    ),
}

SERVER_CAPABILITIES = {
    "tools": {
        "listChanged": False,  # tools are static
    },
}

# ── App Lifecycle ───────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed database on startup."""
    await run_seed()
    logger.info("mcp_server_started", tools=len(MCP_TOOLS_SCHEMA_LIST))
    yield
    logger.info("mcp_server_stopped")


app = FastAPI(
    title="GoodFoods MCP Server",
    description="Model Context Protocol server for restaurant reservation tools",
    version="1.0.0",
    lifespan=lifespan,
)


# ── JSON-RPC Method Handlers ───────────────────────────────────


async def handle_initialize(req_id, params: dict) -> dict:
    """MCP initialize handshake."""
    logger.info("mcp_initialize", client_info=params.get("clientInfo"))
    return make_success_response(req_id, {
        "protocolVersion": "2024-11-05",
        "serverInfo": SERVER_INFO,
        "capabilities": SERVER_CAPABILITIES,
    })


async def handle_tools_list(req_id, params: dict) -> dict:
    """Return all available tool schemas."""
    logger.info("mcp_tools_list", count=len(MCP_TOOLS_SCHEMA_LIST))
    return make_success_response(req_id, {
        "tools": MCP_TOOLS_SCHEMA_LIST,
    })


async def handle_tools_call(req_id, params: dict) -> dict:
    """Dispatch a tool call with validation."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    session_id = params.get("_meta", {}).get("session_id", "mcp-anonymous")

    if not tool_name:
        return make_error_response(
            req_id, INVALID_PARAMS, "Missing 'name' in params"
        )

    # Rate limit check
    if not check_rate_limit(session_id):
        return make_error_response(
            req_id, -32000, "Rate limit exceeded. Max 60 requests/minute."
        )

    # Input validation
    is_valid, error_msg = validate_tool_input(tool_name, arguments)
    if not is_valid:
        return make_error_response(
            req_id, INVALID_PARAMS, error_msg
        )

    logger.info(
        "mcp_tools_call",
        tool=tool_name,
        session_id=session_id,
        arg_keys=list(arguments.keys()),
    )

    # Strip null values — 8B model frequently sends null for optional params
    clean_args = {k: v for k, v in arguments.items() if v is not None}

    try:
        result = await dispatch_tool_call(
            tool_name=tool_name,
            arguments=clean_args,
            session_id=session_id,
        )

        # MCP format: content array with text
        return make_success_response(req_id, {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, default=str),
                }
            ],
            "isError": not result.get("success", False),
        })

    except Exception as exc:
        logger.error(
            "mcp_tool_execution_error",
            tool=tool_name,
            error=str(exc),
        )
        return make_error_response(
            req_id, INTERNAL_ERROR,
            f"Tool execution failed: {str(exc)}",
        )


# ── Method Router ──────────────────────────────────────────────

_METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


# ── Main Endpoint ──────────────────────────────────────────────


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """JSON-RPC 2.0 dispatch endpoint for MCP protocol."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            make_error_response(None, PARSE_ERROR, "Invalid JSON"),
            status_code=400,
        )

    # Validate JSON-RPC structure
    try:
        rpc_req = JsonRpcRequest(**body)
    except Exception as e:
        return JSONResponse(
            make_error_response(
                body.get("id"), INVALID_REQUEST,
                f"Invalid JSON-RPC request: {str(e)}",
            ),
            status_code=400,
        )

    # Route to handler
    handler = _METHOD_HANDLERS.get(rpc_req.method)
    if handler is None:
        return JSONResponse(
            make_error_response(
                rpc_req.id, METHOD_NOT_FOUND,
                f"Unknown method: {rpc_req.method}. "
                f"Available: {', '.join(_METHOD_HANDLERS.keys())}",
            ),
            status_code=404,
        )

    result = await handler(rpc_req.id, rpc_req.params)
    return JSONResponse(result)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "server": SERVER_INFO["name"],
        "version": SERVER_INFO["version"],
        "tools_count": len(MCP_TOOLS_SCHEMA_LIST),
    }
