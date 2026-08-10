@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

where python >nul 2>nul
if errorlevel 1 (
  echo [launcher] python was not found on PATH.
  exit /b 1
)

if not exist ".venv" (
  echo [launcher] creating virtual environment...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo [launcher] ensuring dependencies are installed...
python -m pip install -q -r requirements.txt

echo [launcher] running pre-flight healer...
python modules/preflight.py
if errorlevel 1 (
  echo [launcher] pre-flight checks failed.
  exit /b 1
)

echo [launcher] launching Pantheon Studios control panel...
python modules/control_panel.py
