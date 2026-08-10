@echo off
setlocal
cd /d "%~dp0"
set PY=".venv\Scripts\python.exe"
if not exist %PY% (
    echo Virtual environment not found. Run: py -m venv .venv
    exit /b 1
)
%PY% -m uvicorn app.main:create_app --factory --reload
