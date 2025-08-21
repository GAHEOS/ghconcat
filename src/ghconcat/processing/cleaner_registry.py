from __future__ import annotations
"""LanguageCleanerRegistry

Provide pluggable, language-aware comment/docstring cleaners to decouple
WalkerAppender from per-language conditionals.

This version introduces a formal CleanerProtocol and optional priorities
for future extension (e.g., AST-based JS/TS cleaner).
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol

from ghconcat.processing.docstrip.py_docstrip import strip_comments_and_docstrings
from ghconcat.processing.docstrip.dart_docstrip import strip_dart_comments


class CleanerProtocol(Protocol):
    """Protocol for language-specific cleaners."""
    def strip(self, source: str, *, filename: Optional[str] = None) -> str:
        ...


@dataclass(frozen=True)
class _CleanerRegItem:
    cleaner: CleanerProtocol
    priority: int = 0


class LanguageCleaner(CleanerProtocol):
    """Adapter around a simple call-signature function."""

    def __init__(self, fn: Callable[[str, Optional[str]], str]) -> None:
        self._fn = fn

    def strip(self, source: str, *, filename: Optional[str] = None) -> str:
        return self._fn(source, filename)


class LanguageCleanerRegistry:
    """Registry mapping file suffix → best cleaner (by priority)."""

    def __init__(self) -> None:
        self._by_suffix: Dict[str, _CleanerRegItem] = {}

    @classmethod
    def default(cls) -> 'LanguageCleanerRegistry':
        reg = cls()
        # Default priorities keep current behavior; AST-based cleaners can
        # later be registered with higher values.
        reg.register('.py', LanguageCleaner(lambda s, fn=None: strip_comments_and_docstrings(s, language='py', filename=fn)), priority=0)
        reg.register('.dart', LanguageCleaner(lambda s, fn=None: strip_dart_comments(s)), priority=0)
        return reg

    def register(self, suffix: str, cleaner: CleanerProtocol, *, priority: int = 0) -> None:
        sufx = suffix if suffix.startswith('.') else f'.{suffix}'
        key = sufx.lower()
        prev = self._by_suffix.get(key)
        if prev is None or priority >= prev.priority:
            self._by_suffix[key] = _CleanerRegItem(cleaner=cleaner, priority=priority)

    def for_suffix(self, suffix: str) -> Optional[CleanerProtocol]:
        item = self._by_suffix.get((suffix or '').lower())
        return item.cleaner if item else None