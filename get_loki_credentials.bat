@echo off
setlocal EnableExtensions
title LOKI THE SUN GOD - Credential Finder

echo ============================================================
echo  LOKI THE SUN GOD - Where to get required deployment info
echo ============================================================
echo.
echo This helper does NOT collect or display secrets.
echo It opens the official places where you can copy the values
echo into this file:
echo.
echo   %~dp0.env
echo.
echo Required values still needed:
echo   DISCORD_TOKEN
echo   DISCORD_CLIENT_ID
echo   DISCORD_CLIENT_SECRET
echo   OWNER_ID
echo   TEST_GUILD_ID
echo   Optional hosted deploy: DATABASE_URL / Railway domain
echo.
pause

echo.
echo ============================================================
echo  1. Discord Developer Portal
echo ============================================================
echo.
echo Opened: https://discord.com/developers/applications
echo.
echo In Discord Developer Portal:
echo.
echo   A) Select your LOKI application.
echo      If none exists, click "New Application".
echo.
echo   B) DISCORD_CLIENT_ID
echo      Go to: General Information
echo      Copy: Application ID
echo      Paste into .env as:
echo        DISCORD_CLIENT_ID=
echo.
echo   C) DISCORD_CLIENT_SECRET
echo      Go to: OAuth2
echo      Copy or reset: Client Secret
echo      Paste into .env after:
echo        DISCORD_CLIENT_SECRET=
echo.
echo   D) DISCORD_TOKEN
echo      Go to: Bot
echo      Click: Reset Token / Copy Token
echo      Paste into .env after:
echo        DISCORD_TOKEN=
echo.
echo   E) Privileged Gateway Intents
echo      Go to: Bot
echo      Enable:
echo        MESSAGE CONTENT INTENT
echo        SERVER MEMBERS INTENT
echo.
echo   F) OAuth Redirects
echo      Go to: OAuth2 - General
echo      Add local redirect:
echo        http://127.0.0.1:5000/callback
echo      If deploying online later, also add:
echo        https://YOUR-DOMAIN/callback
echo.
start "" "https://discord.com/developers/applications"
pause

echo.
echo ============================================================
echo  2. Get your Discord user ID and server ID
echo ============================================================
echo.
echo Opened: Discord web app
echo.
echo In Discord:
echo.
echo   A) Enable Developer Mode:
echo      User Settings - Advanced - Developer Mode - ON
echo.
echo   B) OWNER_ID
echo      Right-click your Discord profile/user name.
echo      Click: Copy User ID
echo      Paste into .env as:
echo        OWNER_ID=your_user_id
echo.
echo   C) TEST_GUILD_ID
echo      Right-click your server icon.
echo      Click: Copy Server ID
echo      Paste into .env as:
echo        TEST_GUILD_ID=your_server_id
echo.
echo   D) Optional channel IDs
echo      Right-click important channels and Copy Channel ID.
echo      Useful for logs, admin control, announcements, crawler output.
echo.
start "" "https://discord.com/channels/@me"
pause

echo.
echo ============================================================
echo  3. Invite LOKI to your server
echo ============================================================
echo.
echo After DISCORD_CLIENT_ID is in .env, this script can print
echo an invite URL. It uses common bot permissions, but you can
echo also generate an invite in Developer Portal - OAuth2 - URL Generator.
echo.
set "ENV_FILE=%~dp0.env"
set "CLIENT_ID="
if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if /I "%%A"=="DISCORD_CLIENT_ID" set "CLIENT_ID=%%B"
  )
)
if not defined CLIENT_ID (
  echo DISCORD_CLIENT_ID is not filled in yet.
  echo After you paste it into .env, rerun this batch file.
) else (
  powershell -NoProfile -Command "param([string]$ClientId) if ($ClientId -match '^[0-9]+$') { exit 0 } else { exit 1 }" "%CLIENT_ID%"
  if errorlevel 1 (
    echo DISCORD_CLIENT_ID must contain only digits. Check .env before opening the invite URL.
    exit /b 1
  ) else (
    echo Invite URL:
    echo https://discord.com/oauth2/authorize?client_id=%CLIENT_ID%^&permissions=274877991936^&scope=bot%%20applications.commands
    echo.
    start "" "https://discord.com/oauth2/authorize?client_id=%CLIENT_ID%&permissions=274877991936&scope=bot%%20applications.commands"
  )
)
pause

echo.
echo ============================================================
echo  4. Railway / hosted deploy info, optional
echo ============================================================
echo.
echo Opened: https://railway.app/dashboard
echo.
echo If you want hosted deployment:
echo.
echo   A) Create/select a Railway project.
echo   B) Add a Postgres database.
echo   C) Copy the Postgres connection string into .env or Railway variables:
echo        DATABASE_URL=postgresql://...
echo   D) Copy your Railway public domain and set:
echo        DASHBOARD_PUBLIC_URL=https://YOUR-DOMAIN
echo        REDIRECT_URI=https://YOUR-DOMAIN/callback
echo   E) Add the same hosted REDIRECT_URI to Discord OAuth2 redirects.
echo.
start "" "https://railway.app/dashboard"
pause

echo.
echo ============================================================
echo  5. Open local files/tools
echo ============================================================
echo.
echo Opening .env for editing...
if exist "%ENV_FILE%" (
  start "" notepad "%ENV_FILE%"
) else (
  echo .env does not exist yet at: %ENV_FILE%
)
echo.
echo Opening local dashboard health page...
start "" "http://127.0.0.1:5000/healthz"
echo.
echo When finished filling .env, run this from the project folder:
echo.
echo   .venv\Scripts\python.exe scripts\release_check.py --strict-env
echo.
echo Then restart the dashboard/bot so the new values are loaded.
echo.
pause
endlocal
