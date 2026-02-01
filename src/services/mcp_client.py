"""MCP client helpers (FastMCP)."""
from __future__ import annotations

import json
from typing import Any, Dict

from src.core.config import settings


def _normalize_web_search_result(raw: Any) -> Dict[str, Any]:
    """Extract {query, results, message} from MCP tool result (may be CallToolResult or dict)."""
    out: Dict[str, Any] = {"query": "", "results": [], "message": ""}
    if isinstance(raw, dict):
        out["query"] = raw.get("query", "")
        out["results"] = raw.get("results") if isinstance(raw.get("results"), list) else []
        out["message"] = raw.get("message", "")
        return out
    # FastMCP may return CallToolResult with structured_content or content[].text
    if hasattr(raw, "structured_content") and isinstance(raw.structured_content, dict):
        out["query"] = raw.structured_content.get("query", "")
        out["results"] = raw.structured_content.get("results") if isinstance(raw.structured_content.get("results"), list) else []
        out["message"] = raw.structured_content.get("message", "")
        return out
    if hasattr(raw, "content") and isinstance(raw.content, list) and raw.content:
        first = raw.content[0]
        text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else None)
        if text and isinstance(text, str):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    out["query"] = data.get("query", "")
                    out["results"] = data.get("results") if isinstance(data.get("results"), list) else []
                    out["message"] = data.get("message", "")
            except json.JSONDecodeError:
                pass
    return out


async def call_mcp_web_search(query: str, limit: int = 5) -> Dict[str, Any] | None:
    """Call MCP WebSearch tool if MCP_SERVER_URL is configured. Returns normalized dict or None."""
    if not settings.MCP_SERVER_URL:
        return None
    try:
        from fastmcp import Client
    except Exception:
        return None

    try:
        async with Client(settings.MCP_SERVER_URL) as client:
            result = await client.call_tool(
                name="WebSearch",
                arguments={"query": query, "limit": limit},
            )
        return _normalize_web_search_result(result)
    except Exception:
        return None
