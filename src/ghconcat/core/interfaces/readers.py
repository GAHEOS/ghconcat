from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol, Sequence, runtime_checkable, Optional

from ghconcat.core.models import ReaderHint

Predicate = Callable[[Path], bool]


@runtime_checkable
class ReaderProtocol(Protocol):
    def read_lines(self, path: Path) -> list[str]:
        ...


@runtime_checkable
class ReaderRegistryProtocol(Protocol):
    def register(self, suffixes: Sequence[str], reader: ReaderProtocol) -> None:
        ...

    def register_rule(
            self,
            *,
            reader: ReaderProtocol,
            priority: int = 0,
            suffixes: Sequence[str] | None = None,
            predicate: Predicate | None = None,
            mimes: Sequence[str] | None = None,
    ) -> None:
        ...

    def push(self) -> None:
        ...

    def pop(self) -> None:
        ...

    def read_lines(self, path: Path) -> list[str]:
        ...

    def read_lines_ex(self, path: Path, hint: Optional[ReaderHint] = None) -> list[str]:
        ...
