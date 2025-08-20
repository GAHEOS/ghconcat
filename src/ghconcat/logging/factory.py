from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional, TextIO

from ghconcat.core.interfaces.logging import LoggerFactoryProtocol


class JsonLogFormatter(logging.Formatter):
    """JSON formatter used when json_logs=True.

    Includes an optional 'ctx' field if a ContextLoggerAdapter provided context.
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
        # If a ContextLoggerAdapter is used, 'context' is injected into the record.
        ctx = getattr(record, 'context', None)
        if isinstance(ctx, dict) and ctx:
            payload['ctx'] = ctx

        return json.dumps(payload, ensure_ascii=False)


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Lightweight adapter to attach structured context to log records.

    The attached context is exposed as 'context' on the record and serialized
    by JsonLogFormatter under the 'ctx' key. This is a no-op for plain text logs.
    """

    def __init__(self, logger: logging.Logger, context: Optional[dict] = None) -> None:
        super().__init__(logger, extra=context or {})

    def process(self, msg, kwargs):
        kwargs = kwargs or {}
        extra = kwargs.get('extra') or {}
        # Merge adapter context with call-time extra context
        context = dict(self.extra)
        if 'context' in extra and isinstance(extra['context'], dict):
            context.update(extra['context'])
        kwargs['extra'] = {**extra, 'context': context}
        return msg, kwargs


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

    def with_context(self, logger: logging.Logger, **context) -> ContextLoggerAdapter:
        """Wrap an existing logger with structured context.

        Example:
            factory = DefaultLoggerFactory(json_logs=True)
            lg = factory.with_context(factory.get_logger('ghconcat'), run_id='abc', workspace='/tmp/ws')
            lg.info('Started')  # => {"ctx": {"run_id": "abc", "workspace": "/tmp/ws"}, ...}
        """
        self._ensure_config()
        return ContextLoggerAdapter(logger, context=context)