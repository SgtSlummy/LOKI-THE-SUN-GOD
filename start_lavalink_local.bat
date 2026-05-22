@echo off
setlocal EnableExtensions
title LOKI Local Lavalink

set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_lavalink_local.ps1"
exit /b %errorlevel%
