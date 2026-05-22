@echo off
setlocal EnableExtensions
title Codex - Dolphin Local

set "ROOT=%~dp0"
cd /d "%ROOT%"

docker.exe ps --filter "name=^/ollama$" --filter "status=running" --format "{{.Names}}" | findstr /I /X "ollama" >nul 2>nul
if errorlevel 1 (
  docker.exe ps -a --filter "name=^/ollama$" --format "{{.Names}}" | findstr /I /X "ollama" >nul 2>nul
  if errorlevel 1 (
    echo Ollama is not set up yet. Running setup first...
    call "%ROOT%setup_dolphin_local.bat"
    if errorlevel 1 exit /b 1
  ) else (
    echo Starting existing Ollama container...
    docker.exe start ollama >nul
  )
)

echo Starting Codex with Dolphin local model...
call codex --profile dolphin --oss --local-provider ollama -m dolphin3:8b -C "%ROOT%"
