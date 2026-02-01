@echo off
cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo [maCAD] Starting MCP server (web search) on http://127.0.0.1:8001
echo         Optional: set SERPER_API_KEY in .env for web search.
echo.
python mcp_server\app.py

pause
