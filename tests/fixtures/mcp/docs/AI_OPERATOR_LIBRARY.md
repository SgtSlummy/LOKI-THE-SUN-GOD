# AI Operator Library

LOKI THE SUN GOD uses this library to explain operator-facing behavior without requiring Discord connectivity.

## Local AI

- Ollama direct mode defaults to `http://127.0.0.1:11434`.
- 9router local mode defaults to `http://127.0.0.1:20128/v1`.
- When neither backend is reachable, operator tools should report the gap instead of guessing.

## Command Review

- Prefer slash-capable commands when both slash and prefix flows exist.
- Explain destructive options before suggesting them.
