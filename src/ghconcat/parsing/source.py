from __future__ import annotations
"""Directive source model and error helpers.

This module defines a small, reusable data structure that carries rich
source information (filename, line, column). It is used by the tokenizer
and parser to emit more helpful diagnostics without changing the external
CLI/API behavior.

The structure is intentionally lightweight and does not alter the token
stream payload; it is used *only* for logging/error messages.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DirectiveSource:
    """Represents the origin of a directive token or line.

    Attributes:
        path: Absolute or relative path to the source file if known.
        line: 1-based line number in the source.
        col:  1-based column number in the source line.
    """
    path: Optional[Path] = None
    line: Optional[int] = None
    col: Optional[int] = None

    def format(self) -> str:
        """Return a human-readable source label."""
        parts: list[str] = []
        if self.path:
            parts.append(str(self.path))
        if self.line is not None:
            parts.append(f"line {self.line}")
        if self.col is not None:
            parts.append(f"col {self.col}")
        return ":".join(parts) if parts else "<cli>"

    def with_line_col(self, line: int, col: int | None = None) -> "DirectiveSource":
        """Return a copy with given line/col updated."""
        return DirectiveSource(path=self.path, line=line, col=col)