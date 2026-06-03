from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging(level: str) -> logging.Logger:
    normalized = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=normalized,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger("loki")


def log_safe_startup_config(logger: logging.Logger, config: dict[str, Any]) -> None:
    logger.info("Startup config: %s", json.dumps(config, sort_keys=True))

