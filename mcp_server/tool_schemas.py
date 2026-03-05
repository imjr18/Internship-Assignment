"""
Module: mcp_server/tool_schemas.py
Responsibility: MCP-format tool schemas for all 8 GoodFoods tools.

Converts the Groq/Llama tool schemas into the MCP (Model Context Protocol)
format expected by `tools/list` responses.

MCP schema format:
  {
    "name": "tool_name",
    "description": "...",
    "inputSchema": { "type": "object", "properties": {...}, "required": [...] }
  }
"""

from __future__ import annotations

from config.prompts import TOOL_SCHEMAS


def _groq_to_mcp(groq_schema: dict) -> dict:
    """Convert a single Groq/Llama tool schema to MCP format."""
    fn = groq_schema["function"]
    return {
        "name": fn["name"],
        "description": fn["description"],
        "inputSchema": fn["parameters"],
    }


def get_mcp_tool_schemas() -> list[dict]:
    """Return all tool schemas in MCP format."""
    return [_groq_to_mcp(s) for s in TOOL_SCHEMAS]


# Pre-built list for fast access
MCP_TOOLS_SCHEMA_LIST: list[dict] = get_mcp_tool_schemas()
