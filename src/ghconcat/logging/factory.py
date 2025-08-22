from __future__ import annotations

import logging
from typing import Optional, TextIO

from ghconcat.logging.helpers import setup_base_logger, get_logger


class DefaultLoggerFactory:
    """Factory that configures and returns project-scoped loggers.

    This implementation delegates base configuration to `setup_base_logger`
    in order to avoid duplication and keep behavior centralized.
    """

    def __init__(self, *, json_logs: bool = False, level: int = logging.INFO, stream: Optional[TextIO] = None) -> None:
        self._json = bool(json_logs)
        self._level = int(level)
        self._stream: Optional[TextIO] = stream
        self._configured = False

    def _ensure_config(self) -> None:
        if self._configured:
            return
        setup_base_logger(json_logs=self._json, level=self._level, stream=self._stream)
        self._configured = True

    def get_logger(self, name: str) -> logging.Logger:
        self._ensure_config()
        # Route through helper to keep naming unified.
        return get_logger(name)