from __future__ import annotations

import platform

# Windows WMI-backed platform detection can hang in constrained automation shells
# while importing aiohttp/discord.py during test collection. The suite does not
# depend on live OS probing, so keep collection deterministic.
platform.system = lambda: "Windows"
