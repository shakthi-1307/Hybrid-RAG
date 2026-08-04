"""Process-wide logging configuration. Called once from the application lifespan."""

from __future__ import annotations

import logging
import sys

from app.config import settings


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)
