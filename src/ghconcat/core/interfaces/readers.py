from pathlib import Path
from typing import Callable, Protocol, Sequence

# Predicate matches concrete implementation semantics: Callable[[Path], bool]
Predicate = Callable[[Path], bool]


class ReaderProtocol(Protocol):
    """Read file-like content and return text lines (UTF-8, with trailing '\\n').

    Implementations should not raise on binary/unsupported files; they should
    return an empty list when the content cannot be decoded or is unsupported.
    """

    def read_lines(self, path: Path) -> list[str]: ...


class ReaderRegistryProtocol(Protocol):
    """Registry with suffix/predicate rules and a default reader fallback.

    This Protocol mirrors the surface actually used by ghconcat components:
      • register(...)     – suffix-to-reader mapping
      • register_rule(...)– advanced, optional predicate-based rules
      • push()/pop()      – reversible, scoped mappings (temporary overrides)
      • read_lines(...)   – unified entrypoint to read files as text lines
    """

    def register(self, suffixes: Sequence[str], reader: ReaderProtocol) -> None: ...

    def register_rule(
            self,
            *,
            reader: ReaderProtocol,
            priority: int = 0,
            suffixes: Sequence[str] | None = None,
            predicate: Predicate | None = None,
    ) -> None: ...

    def push(self) -> None: ...

    def pop(self) -> None: ...

    def read_lines(self, path: Path) -> list[str]: ...