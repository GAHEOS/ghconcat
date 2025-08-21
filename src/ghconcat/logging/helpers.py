from __future__ import annotations
"""Small logging helpers to standardize ghconcat logger names and tracing."""

import logging
import os


def get_logger(name: str | None = None) -> logging.Logger:
    if not name or name == "ghconcat":
        return logging.getLogger("ghconcat")
    if name.startswith("ghconcat"):
        return logging.getLogger(name)
    return logging.getLogger(f"ghconcat.{name}")


def is_trace_io_enabled() -> bool:
    """Return True when low-level IO tracing is enabled via env flag."""
    return os.getenv("GHCONCAT_TRACE_IO") == "1"


def trace_io(logger: logging.Logger, message: str, **ctx) -> None:
    """Emit a DEBUG-level tracing line if GHCONCAT_TRACE_IO=1 is set.

    The function is a no-op by default and never raises.
    """
    if not is_trace_io_enabled():
        return
    if ctx:
        try:
            logger.debug("%s | ctx=%r", message, ctx)
        except Exception:
            logger.debug("%s", message)
    else:
        logger.debug("%s", message)