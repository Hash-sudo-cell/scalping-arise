"""
Scalping Arise — Structured Logging Foundation

Provides consistent, structured logging across the application.
Logs are formatted for readability in development and machine-parseable
in production.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logging(
    level: str = "INFO",
    fmt: Optional[str] = None,
    environment: str = "development",
) -> None:
    """
    Configure application-wide logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: Custom format string. Uses default if None.
        environment: Current environment for format selection.
    """
    if fmt is None:
        if environment == "production":
            fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        else:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to prevent duplicate logs
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    logging.info(
        "Logging initialized | level=%s | environment=%s",
        level.upper(),
        environment,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger for a specific module.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
