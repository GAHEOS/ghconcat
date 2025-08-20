from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ghconcat.io.readers import FileReader
from ghconcat.core.interfaces.readers import ReaderRegistryProtocol


@dataclass
class ReaderMappingScope:
    """Context manager to temporarily override reader mappings in a registry.

    Example:
        with ReaderMappingScope(registry) as scope:
            scope.register(['.html'], HtmlToTextReader())
            # ... do work with temporary mapping ...
        # mappings restored automatically
    """
    registry: ReaderRegistryProtocol

    def __enter__(self) -> "ReaderMappingScope":
        self.registry.push()
        return self

    def register(self, suffixes: Sequence[str], reader: FileReader) -> "ReaderMappingScope":
        self.registry.register(suffixes, reader)
        return self

    def register_rule(
        self,
        *,
        reader: FileReader,
        priority: int = 0,
        suffixes: Sequence[str] | None = None,
        predicate: Callable[[Path], bool] | None = None,
        mimes: Sequence[str] | None = None,
    ) -> "ReaderMappingScope":
        """Forward `register_rule` to the underlying registry within the scope."""
        self.registry.register_rule(
            reader=reader, priority=priority, suffixes=suffixes, predicate=predicate, mimes=mimes
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.registry.pop()