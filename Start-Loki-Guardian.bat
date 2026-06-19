@echo off
setlocal
cd /d "%~dp0"
rem Local Windows guardian uses SQLite because Railway private Postgres is not reachable from this shell.
set "DATABASE_URL=sqlite:///loki-relay.db"
set "BOT_ENV=development"
python -m scripts.loki_guardian
pause
