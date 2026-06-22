@echo off
setlocal
set "INSTALL_ROOT={{INSTALL_ROOT}}"
set "NODE_ENV_FILE=%INSTALL_ROOT%\loki-node.env"
set "BRIDGE_PORT={{BRIDGE_PORT}}"
set "HERMES_API_PORT={{HERMES_API_PORT}}"
cd /d "%INSTALL_ROOT%"

REM Load simple KEY=VALUE env file without echoing secrets.
for /f "usebackq tokens=1,* delims==" %%A in ("%NODE_ENV_FILE%") do (
  if not "%%A"=="" if not "%%A:~0,1"=="#" set "%%A=%%B"
)

REM Keep Ollama available for backup and cron tasks.
start "Ollama backup LLM" /min ollama serve

REM Faust-compatible bridge used by Loki /agent council and /agent maintain.
start "Loki Hermes Bridge" /min python "%INSTALL_ROOT%\scripts\loki_hermes_bridge.py" --host 127.0.0.1 --port %BRIDGE_PORT% --env "%NODE_ENV_FILE%"

REM Loki Discord bot itself, supervised by its guardian when the repo was bundled/copied.
if exist "%INSTALL_ROOT%\LokiBot\scripts\loki_guardian.py" (
  cd /d "%INSTALL_ROOT%\LokiBot"
  start "Loki Discord Bot Guardian" /min python -m scripts.loki_guardian
  cd /d "%INSTALL_ROOT%"
)

REM Optional Hermes API/gateway process for Hermexj/iOS access through Tailscale.
where hermes >nul 2>nul
if not errorlevel 1 (
  start "Hermes Gateway" /min hermes --profile %HERMES_PROFILE% gateway run
)
