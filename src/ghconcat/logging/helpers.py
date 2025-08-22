from __future__ import annotations

"""Small logging helpers to standardize ghconcat logger names, configuration and tracing.

This module provides:
    - JsonLogFormatter: JSON log formatter with stable fields and optional context.
    - setup_base_logger: Root logger configuration for the 'ghconcat' logger.
    - get_logger: Namespaced logger factory ('ghconcat.*').
    - trace_io utilities gated by GHCONCAT_TRACE_IO.

Changes (telemetry):
    - Added a fixed 'version' field to the JSON payload, resolved from
      ghconcat.__version__ and cached at formatter construction time.

Design notes:
    - We resolve the version lazily and safely to avoid circular imports.
    - Fallback to 'unknown' if the version cannot be imported.
"""

import logging
import os
from typing import Optional, TextIO


class JsonLogFormatter(logging.Formatter):
    """Emit logs as compact JSON with a fixed schema.

    Fields:
        - ts: ISO-8601 timestamp in UTC with millisecond precision.
        - level: Log level name.
        - module: Logger name (e.g., 'ghconcat.exec').
        - msg: Formatted message string.
        - version: ghconcat.__version__ (fixed per formatter instance).
        - ctx: Optional dictionary attached to the record as 'context'.
    """

    def __init__(self) -> None:
        super().__init__()
        self._version = self._resolve_version()

    @staticmethod
    def _resolve_version() -> str:
        """Resolve ghconcat version safely to avoid import cycles.

        Returns:
            str: Version string or 'unknown' if it cannot be determined.
        """
        try:
            # Lazy import to reduce the chance of circular imports at import time.
            from ghconcat import __version__ as _v  # type: ignore
            return str(_v)
        except Exception:
            # Optional fallback via environment for custom packaging scenarios.
            return os.getenv("GHCONCAT_VERSION", "unknown")

    def format(self, record: logging.LogRecord) -> str:
        from datetime import datetime, timezone
        import json

        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        payload = {
            "ts": ts_str,
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
            "version": self._version,
        }

        ctx = getattr(record, "context", None)
        if isinstance(ctx, dict) and ctx:
            payload["ctx"] = ctx

        return json.dumps(payload, ensure_ascii=False)


def setup_base_logger(
    *, json_logs: bool = False, level: int = logging.INFO, stream: Optional[TextIO] = None
) -> logging.Logger:
    """Configure the base 'ghconcat' logger once and return it.

    Args:
        json_logs: If True, configure a JSON formatter, else plain text.
        level: Logging level for the base logger.
        stream: Optional stream (stderr by default).

    Returns:
        The configured base logger.
    """
    base = logging.getLogger("ghconcat")
    if base.handlers:
        base.setLevel(level)
        return base

    import sys as _sys

    base.handlers.clear()
    base.setLevel(level)
    base.propagate = False

    handler = logging.StreamHandler(stream or _sys.stderr)
    if json_logs:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    base.addHandler(handler)

    return base


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced logger under 'ghconcat'."""
    if not name or name == "ghconcat":
        return logging.getLogger("ghconcat")
    if name.startswith("ghconcat"):
        return logging.getLogger(name)
    return logging.getLogger(f"ghconcat.{name}")


def is_trace_io_enabled() -> bool:
    """Check if IO tracing is enabled via env flag."""
    return os.getenv("GHCONCAT_TRACE_IO") == "1"


def trace_io(logger: logging.Logger, message: str, **ctx) -> None:
    """Emit debug-verbosity IO trace messages only when enabled.

    Args:
        logger: Target logger.
        message: Human-readable description.
        **ctx: Optional structured context that will be appended in debug format.
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