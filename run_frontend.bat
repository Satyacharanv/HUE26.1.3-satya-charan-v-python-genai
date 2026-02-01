@echo off
cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo.
echo [maCAD] Starting Streamlit frontend on http://localhost:8501
echo.
streamlit run streamlit_app/main.py --server.port 8501

pause
