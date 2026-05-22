@echo off
setlocal EnableExtensions
title Setup Dolphin Local Model

set "ROOT=%~dp0"
set "MODEL=dolphin3:8b"
set "OLLAMA_HOST=http://127.0.0.1:11434"

where docker.exe >nul 2>nul
if errorlevel 1 (
  echo docker.exe was not found. Install/open Docker Desktop, then run this file again.
  pause
  exit /b 1
)

echo Checking Docker...
docker.exe version
if errorlevel 1 (
  echo Docker is not available. Open Docker Desktop, wait for it to finish starting, then run this file again.
  pause
  exit /b 1
)

set "OLLAMA_EXISTS="
for /f "delims=" %%A in ('docker.exe ps -a --filter "name=^/ollama$" --format "{{.Names}}" 2^>nul') do set "OLLAMA_EXISTS=%%A"

if /I "%OLLAMA_EXISTS%"=="ollama" (
  echo Starting existing Ollama container...
  docker.exe start ollama
) else (
  echo Creating Ollama Docker container...
  docker.exe run -d --name ollama -p 127.0.0.1:11434:11434 -v ollama:/root/.ollama ollama/ollama
)
if errorlevel 1 (
  echo.
  echo Could not start the Ollama container.
  pause
  exit /b 1
)

echo Waiting for Ollama API...
for /L %%I in (1,1,30) do (
  curl.exe -fsS "%OLLAMA_HOST%/api/tags" >nul 2>nul && goto ollama_ready
  timeout /t 1 /nobreak >nul
)

echo Ollama did not become available at %OLLAMA_HOST%.
pause
exit /b 1

:ollama_ready
echo Pulling %MODEL%. This can take a while the first time...
docker.exe exec ollama ollama pull %MODEL%
if errorlevel 1 (
  echo.
  echo Could not pull %MODEL%.
  pause
  exit /b 1
)

echo Updating project .env...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\setup_dolphin_local.ps1" -SkipDocker
if errorlevel 1 (
  echo.
  echo Docker setup worked, but .env update failed.
  pause
  exit /b 1
)

echo.
echo Setup complete.
echo.
echo Use codex_models.bat to choose Dolphin local or OpenAI Codex.
pause
