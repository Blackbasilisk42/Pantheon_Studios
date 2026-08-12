@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

if "%~1"=="" (
  echo Usage: site_control.bat ^<start-all^|start^|stop^|enable^|disable^|master-killswitch^|status^> [args]
  echo Example: site_control.bat stop team_hub
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [site-control] python was not found on PATH.
  exit /b 1
)

if not exist ".venv" (
  echo [site-control] creating virtual environment...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"
python scripts/site_launcher.py %*
