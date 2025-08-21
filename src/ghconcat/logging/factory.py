from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional, TextIO

from ghconcat.core.interfaces.logging import LoggerFactoryProtocol


class JsonLogFormatter(logging.Formatter):
    """JSON formatter used when json_logs=True.

    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = ts.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

        payload = {
            'ts': ts_str,
            'level': record.levelname,
            'module': record.name,
            'msg': record.getMessage(),
        }
        ctx = getattr(record, 'context', None)
        if isinstance(ctx, dict) and ctx:
            payload['ctx'] = ctx

        return json.dumps(payload, ensure_ascii=False)


class DefaultLoggerFactory(LoggerFactoryProtocol):
    def __init__(self, *, json_logs: bool = False, level: int = logging.INFO, stream: Optional[TextIO] = None) -> None:
        self._json = bool(json_logs)
        self._level = int(level)
        self._stream: TextIO = stream or sys.stderr
        self._configured = False

    def _ensure_config(self) -> None:
        if self._configured:
            return
        base = logging.getLogger('ghconcat')
        base.handlers.clear()
        base.setLevel(self._level)
        base.propagate = False
        handler = logging.StreamHandler(self._stream)
        if self._json:
            handler.setFormatter(JsonLogFormatter())
        else:
            handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        base.addHandler(handler)
        self._configured = True

    def get_logger(self, name: str) -> logging.Logger:
        """Return a standard logger under the 'ghconcat' namespace."""
        self._ensure_config()
        if not name or name == 'ghconcat':
            return logging.getLogger('ghconcat')
        if not name.startswith('ghconcat'):
            return logging.getLogger(f'ghconcat.{name}')
        return logging.getLogger(name)
