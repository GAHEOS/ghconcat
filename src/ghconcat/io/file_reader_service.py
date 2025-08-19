"""
file_reader_service – Thin file reading facade for ghconcat.

This small service encapsulates file reading by delegating to a provided
ReaderRegistry instance (Protocol-based). It exposes a stable
`read_lines(Path) -> list[str]` function suitable for dependency injection
in collaborators such as WalkerAppender, avoiding any implicit reliance on
process-global state.
"""

import logging
from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.readers import ReaderRegistryProtocol
from ghconcat.io.readers import get_global_reader_registry


class FileReadingService:
    """Facade over a ReaderRegistryProtocol to read files as text lines.

    Parameters
    ----------
    registry:
        Explicit registry to use. If omitted, the process-global registry
        is used for backwards compatibility.
    logger:
        Optional logger for homogeneous logs.
    """

    def __init__(
        self,
        registry: Optional[ReaderRegistryProtocol] = None,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.filereader")
        self._registry: ReaderRegistryProtocol = registry or get_global_reader_registry(self._log)

    def read_lines(self, path: Path) -> list[str]:
        """Return *path* contents as lines using the configured registry.

        Parameters
        ----------
        path:
            Filesystem path to read.

        Returns
        -------
        list[str]
            Text lines terminated with '\\n' as returned by the underlying reader.
        """
        return self._registry.read_lines(path)

    @property
    def registry(self) -> ReaderRegistryProtocol:
        """Expose the underlying registry (read-only reference)."""
        return self._registry