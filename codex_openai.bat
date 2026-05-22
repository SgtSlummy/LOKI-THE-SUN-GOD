@echo off
setlocal EnableExtensions
title Codex - OpenAI

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo Starting Codex with hosted OpenAI Codex model...
call codex --profile openai -m gpt-5.5 -C "%ROOT%"
