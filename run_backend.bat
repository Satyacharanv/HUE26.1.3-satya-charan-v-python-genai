@echo off
cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo [maCAD] Starting FastAPI backend on http://localhost:8000
echo         API docs: http://localhost:8000/docs
echo.
uvicorn src.main:app --reload --port 8000

pause
