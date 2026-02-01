# maCAD MCP Server (FastMCP)

This folder contains a FastMCP server that exposes a simple web search tool.

## Run (SSE transport)

```bash
python app.py
```

By default it attempts to use SSE transport (`transport="sse"`). If your FastMCP
version doesn't accept the `transport` argument, the server falls back to
`mcp.run()` automatically.

## Configuration

The built-in `WebSearch` tool uses Serper if `SERPER_API_KEY` is set:

```
SERPER_API_KEY=your_key
```

## MCP client usage

In the main app, set:

```
MCP_SERVER_URL=http://localhost:8000
```

(Update the URL/port to match the FastMCP server output.)
