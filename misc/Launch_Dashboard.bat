@echo off
title Result Finder Dashboard
echo [1/2] Connecting to Local Environment...
cd /d "%~dp0"
echo [2/2] Launching Premium Web Dashboard...
python -m streamlit run app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Failed to start. Make sure Streamlit is installed.
    echo Try running: pip install streamlit pandas
    pause
)
