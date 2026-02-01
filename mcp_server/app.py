"""FastMCP server for maCAD tools (SSE transport)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP

# Load project root .env so SERPER_API_KEY etc. are available when MCP runs as separate process
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


mcp = FastMCP("maCAD MCP")


@mcp.tool
async def WebSearch(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Simple web search tool.
    If SERPER_API_KEY is set, uses Serper. Otherwise returns an empty list.
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return {"query": query, "results": [], "message": "SERPER_API_KEY not configured"}

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": limit}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            return {"query": query, "results": [], "message": f"Serper error: {resp.status_code}"}
        data = resp.json()
        organic = data.get("organic", []) or []
        results: List[Dict[str, Any]] = []
        for item in organic[:limit]:
            results.append({
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
            })
        return {"query": query, "results": results}


if __name__ == "__main__":
    # SSE transport is recommended for web clients.
    # If your FastMCP version doesn't accept "transport", remove the arg.
    try:
        mcp.run(transport="sse", host="127.0.0.1", port=8001)
    except TypeError:
        mcp.run()
