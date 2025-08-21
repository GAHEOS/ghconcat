from __future__ import annotations
"""Abstraction over the global ReaderRegistry.

This service is a thin façade so downstream components do not need to
depend directly on the registry implementation. It preserves permissive
behavior for `read_lines_ex` when the underlying registry does not
implement the extended variant.
"""
import logging
from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.readers import ReaderRegistryProtocol
from ghconcat.core.models import ReaderHint
from ghconcat.io.readers import get_global_reader_registry
from ghconcat.logging.helpers import get_logger


class FileReadingService:
    def __init__(self, registry: Optional[ReaderRegistryProtocol] = None, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or get_logger('io.filereader')
        self._registry: ReaderRegistryProtocol = registry or get_global_reader_registry(self._log)

    def read_lines(self, path: Path) -> list[str]:
        return self._registry.read_lines(path)

    def read_lines_ex(self, path: Path, *, hint: Optional[ReaderHint] = None) -> list[str]:
        meth = getattr(self._registry, 'read_lines_ex', None)
        if callable(meth):
            return meth(path, hint)
        return self._registry.read_lines(path)

    @property
    def registry(self) -> ReaderRegistryProtocol:
        return self._registry