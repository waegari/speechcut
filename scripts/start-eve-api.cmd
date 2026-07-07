@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\pythonw.exe" (
  echo pythonw not found: %CD%\.venv\Scripts\pythonw.exe 1>&2
  exit /b 1
)
".venv\Scripts\pythonw.exe" -m uvicorn eve.api.main:app --host 127.0.0.1 --port 8001
exit /b %ERRORLEVEL%
