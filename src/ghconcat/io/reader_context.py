"""
reader_context – Scoped, reversible reader mapping for ghconcat.
This module provides a small context manager that applies temporary
suffix→reader mappings to a ReaderRegistry and restores the previous
state automatically on exit.

It enables per-execution or per-context HTML textification (-K) without
mutating the process-wide global registry permanently.
"""
from dataclasses import dataclass
from typing import Sequence

from ghconcat.io.readers import FileReader
from ghconcat.core.interfaces.readers import ReaderRegistryProtocol


@dataclass
class ReaderMappingScope:
    """Context manager to apply temporary suffix→reader mappings.

    Example:
        reg = ...  # any ReaderRegistryProtocol
        with ReaderMappingScope(reg).register([".html", ".htm"], HtmlToTextReader()):
            ...  # read files using the temporary mapping

    Notes
    -----
    • Internally uses the ReaderRegistry.push() / pop() stack API (Protocol).
    • Multiple .register(...) calls within the same scope are supported.
    """
    registry: ReaderRegistryProtocol

    def __enter__(self) -> "ReaderMappingScope":
        self.registry.push()
        return self

    def register(self, suffixes: Sequence[str], reader: FileReader) -> "ReaderMappingScope":
        """Register *reader* for given *suffixes* in the active frame."""
        self.registry.register(suffixes, reader)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.registry.pop()