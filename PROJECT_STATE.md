# PANTHEON STUDIOS - WORKSPACE CONTEXT & STATE

## 1. Project Architecture & Current Status
- **Main Project:** `Pantheon_Studios` (Backend tools, `Modelfile`, `modules/preflight.py`, `.venv`).
- **Web Strategy:** All old broken web server launchers (`run.py`, `site_launcher.py`, `.bat` wrappers) were removed.
- **Standalone Public Site:** Located in `standalone_team_site/`. Completely isolated HTML/CSS/JS with no backend dependencies.
- **Future Admin Portal:** Will be built later as a separate middleman layer between the standalone public site and the backend.

## 2. Public Site Visual & Design System
- **Theme:** Cyberpunk Tactical HUD / Sci-Fi Portal.
- **Palette:**
  - Background Void: `#05070a`
  - Neon Emerald (Status/Telemetry): `#00ff9d`
  - Neon Cyan (Borders/Buttons/Reticles): `#00e5ff`
  - Neon Pink (Media/Highlights): `#ff007f`
- **Features:** CRT scanlines, angled clip-paths, live UTC clock, tactical filter buttons, terminal comms simulator, audio synthesizer, and interactive HUD cursor.

## 3. Strict Development Rules for AI Assistant
- **Safety Boundary:** Never execute OS-level shutdown, reboot, or system-wide commands. Keep all edits inside `Pantheon_Studios`.
- **No Over-Engineering:** Avoid multi-file background launcher wrappers, complex PID managers, or daemon loops.
- **Standalone Preservation:** Keep `standalone_team_site/` self-contained. Do not re-attach web runners to root backend code unless explicitly requested.