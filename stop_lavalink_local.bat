@echo off
setlocal EnableExtensions
title Stop LOKI Local Lavalink

set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\stop_lavalink_local.ps1"
exit /b %errorlevel%
