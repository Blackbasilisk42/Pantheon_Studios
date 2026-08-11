@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
if not exist ".venv" (
  echo [hub] creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install -q fastapi uvicorn sqlalchemy python-jose passlib bcrypt python-multipart jinja2 requests
start "Pantheon Hub Server" cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn server:app --host 0.0.0.0 --port 7861"
start "Pantheon Hub Tunnel" cmd /k "call .venv\Scripts\activate.bat && python tunnel.py"
exit /b 0
