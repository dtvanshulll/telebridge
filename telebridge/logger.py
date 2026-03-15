"""Logging helpers with ANSI color output."""

from __future__ import annotations

import logging
import os
import sys
from typing import Final

RESET: Final[str] = "\033[0m"
COLORS: Final[dict[int, str]] = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[35m",
}


def _supports_color(stream: object) -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


class ColorFormatter(logging.Formatter):
    """Add color and a concise production-friendly format to log records."""

    def __init__(self, *, use_color: bool) -> None:
        super().__init__("[%(levelname)s] %(message)s")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = COLORS.get(record.levelno, "") if self.use_color else ""
        return f"{color}{base}{RESET}" if color else base


def configure_logging(level: str | int = logging.INFO, logger_name: str = "telebridge") -> logging.Logger:
    """Configure and return the shared telebridge logger."""

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    if logger.handlers:
        for handler in logger.handlers:
            handler.setFormatter(ColorFormatter(use_color=_supports_color(getattr(handler, "stream", None))))
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter(use_color=_supports_color(sys.stdout)))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
