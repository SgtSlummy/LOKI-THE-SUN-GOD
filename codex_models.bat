@echo off
setlocal EnableExtensions
title Codex Model Launcher

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ============================================================
echo  Codex Model Launcher
echo ============================================================
echo.
echo  1. Start 9Router       ^(Dolphin local router^)
echo  2. Dolphin direct      ^(Ollama / Docker^)
echo  3. OpenAI Codex        ^(hosted^)
echo  4. Setup Dolphin local
echo  5. Setup 9Router
echo  6. Stop 9Router
echo  7. Reset 9Router password
echo  8. Open LOKI AI dashboard
echo.
choice /C 12345678 /N /M "Choose 1, 2, 3, 4, 5, 6, 7, or 8: "

if errorlevel 8 goto dashboard
if errorlevel 7 goto resetrouter
if errorlevel 6 goto stoprouter
if errorlevel 5 goto setuprouter
if errorlevel 4 goto setupdolphin
if errorlevel 3 goto openai
if errorlevel 2 goto dolphin
if errorlevel 1 goto startrouter

:startrouter
call "%ROOT%start_9router_background.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:dolphin
call "%ROOT%codex_dolphin.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:openai
call "%ROOT%codex_openai.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:setupdolphin
call "%ROOT%setup_dolphin_local.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:setuprouter
call "%ROOT%setup_9router.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:stoprouter
call "%ROOT%stop_9router.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:resetrouter
call "%ROOT%reset_9router_password.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%

:dashboard
call "%ROOT%start_loki_ai_dashboard.bat"
set "RESULT=%errorlevel%"
echo.
pause
exit /b %RESULT%
