import logging
from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.readers import ReaderRegistryProtocol
from ghconcat.core.models import ReaderHint
from ghconcat.io.readers import get_global_reader_registry


class FileReadingService:
    """Service that delegates to a ReaderRegistry (global by default)."""

    def __init__(self, registry: Optional[ReaderRegistryProtocol] = None, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger('ghconcat.filereader')
        self._registry: ReaderRegistryProtocol = registry or get_global_reader_registry(self._log)

    def read_lines(self, path: Path) -> list[str]:
        """Backward-compatible entry point used across the codebase."""
        return self._registry.read_lines(path)

    def read_lines_ex(self, path: Path, *, hint: Optional[ReaderHint] = None) -> list[str]:
        """Extended read that forwards MIME/sample hints when supported."""
        meth = getattr(self._registry, 'read_lines_ex', None)
        if callable(meth):
            return meth(path, hint)
        # Fallback to standard behavior if registry does not support hints.
        return self._registry.read_lines(path)

    @property
    def registry(self) -> ReaderRegistryProtocol:
        return self._registry