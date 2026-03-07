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

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager

# ── Windows fix: ProactorEventLoop breaks Groq SDK streaming ───
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import structlog

from database.seed_data import run_seed
from agent.tool_dispatcher import dispatch_tool_call_local
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
    try:
        from tools.recommendations import warmup_search_assets
        warmup_search_assets()
    except Exception as exc:
        logger.warning("startup_warmup_failed", error=str(exc))
    logger.info("mcp_server_started", tools=len(MCP_TOOLS_SCHEMA_LIST))
    yield
    logger.info("mcp_server_stopped")


app = FastAPI(
    title="GoodFoods MCP Server",
    description="Model Context Protocol server for restaurant reservation tools",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — allow Next.js frontend ──────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Session Store — agent instances for Next.js frontend ───────

_chat_sessions: dict[str, object] = {}


def _get_agent(session_id: str):
    from agent.orchestrator import AgentOrchestrator
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = AgentOrchestrator(
            session_id=session_id
        )
    return _chat_sessions[session_id]


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
        # Important: execute locally inside MCP server to avoid recursive
        # HTTP calls back into /mcp.
        result = await dispatch_tool_call_local(
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


# ═══════════════════════════════════════════════════════════════
# NEXT.JS FRONTEND ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@app.post("/chat")
async def chat_stream(request: Request):
    """
    Streaming chat endpoint for Next.js frontend.
    Accepts: {"session_id": str, "message": str}
    Returns: Server-Sent Events stream
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json body"}, status_code=400)
    session_id = body.get("session_id", str(uuid.uuid4()))
    message = body.get("message", "").strip()

    if not message:
        return JSONResponse({"error": "empty message"}, status_code=400)

    async def event_stream():
        emitted_text_token = False
        try:
            agent = _get_agent(session_id)
            async for event in agent.handle_message(message):
                etype = event.get("type", "")
                if etype == "token":
                    text = event.get("content", "")
                    if text:
                        emitted_text_token = True
                        payload = json.dumps({"token": text})
                        yield f"data: {payload}\n\n"
                elif etype == "tool_start":
                    tool_name = event.get("tool_name", "unknown")
                    payload = json.dumps(
                        {"token": f"[TOOL_START:{tool_name}]"}
                    )
                    yield f"data: {payload}\n\n"
                elif etype == "tool_result":
                    tool_name = event.get("tool_name", "unknown")
                    result_data = event.get("result", {})
                    # Check for booking create/modify completion
                    if (
                        tool_name in {"create_reservation", "modify_reservation"}
                        and isinstance(result_data, dict)
                        and result_data.get("success")
                    ):
                        booking_payload = json.dumps(
                            {"token": f"[BOOKING_COMPLETE:{json.dumps(result_data)}]"}
                        )
                        yield f"data: {booking_payload}\n\n"
                    payload = json.dumps(
                        {"token": f"[TOOL_END:{tool_name}]"}
                    )
                    yield f"data: {payload}\n\n"
                elif etype == "error":
                    error_msg = event.get("error", "Unknown error")
                    payload = json.dumps({"error": error_msg})
                    yield f"data: {payload}\n\n"
                elif etype == "done":
                    # Fallback: if the agent produced only a final content
                    # (no streamed token chunks), still surface it to the UI.
                    if not emitted_text_token:
                        final_content = str(event.get("final_content", "") or "").strip()
                        if final_content:
                            payload = json.dumps({"token": final_content})
                            yield f"data: {payload}\n\n"
        except Exception as e:
            import traceback
            logger.error("chat_stream_error", error=str(e), traceback=traceback.format_exc())
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/restaurants")
async def get_restaurants_for_frontend():
    """
    Returns all restaurants for the Next.js Browse screen.
    Parses JSON string fields into proper arrays for JavaScript.
    """
    from database.queries import get_all_restaurants
    import json as _json

    raw = await get_all_restaurants()
    result = []
    for r in raw:
        try:
            dietary = _json.loads(
                r.get("dietary_certifications", "[]") or "[]"
            )
        except Exception:
            dietary = []
        try:
            ambiance = _json.loads(
                r.get("ambiance_tags", "[]") or "[]"
            )
        except Exception:
            ambiance = []
        try:
            hours = _json.loads(
                r.get("operating_hours", "{}") or "{}"
            )
        except Exception:
            hours = {"open": "17:00", "close": "23:00"}

        result.append({
            "id": r["id"],
            "name": r["name"],
            "neighborhood": r.get("neighborhood", ""),
            "cuisine_type": r.get("cuisine_type", ""),
            "price_range": r.get("price_range", 2),
            "total_capacity": r.get("total_capacity", 0),
            "dietary_certifications": dietary,
            "ambiance_tags": ambiance,
            "operating_hours": hours,
            "description": r.get("description", ""),
        })
    return result


@app.get("/booking-state/{session_id}")
async def get_booking_state(session_id: str):
    """
    Returns current booking state for a session.
    Next.js polls this to update the context panel.
    """
    if session_id not in _chat_sessions:
        return {
            "restaurant_name": None,
            "party_size": None,
            "date": None,
            "time": None,
            "conversation_state": "GREETING",
            "confirmation_code": None,
        }
    agent = _chat_sessions[session_id]
    try:
        state = agent.context.get_booking_state()
        return {
            "restaurant_name": state.get("restaurant_name"),
            "party_size": state.get("party_size"),
            "date": state.get("date"),
            "time": state.get("time"),
            "conversation_state": agent.context.get_conversation_state(),
            "confirmation_code": state.get("confirmation_code"),
        }
    except Exception:
        return {
            "restaurant_name": None,
            "party_size": None,
            "date": None,
            "time": None,
            "conversation_state": "GREETING",
            "confirmation_code": None,
        }

