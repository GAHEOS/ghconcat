from __future__ import annotations
"""
LanguageCleanerRegistry

Provide pluggable, language-aware comment/docstring cleaners to decouple
WalkerAppender from per-language conditionals.

This version enhances the registry with **lazy registration**: you can register
a suffix with a builder callback that will be invoked on first access.
If no cleaner exists for a suffix, the walker falls back to the regex-based
pipeline (COMMENT_RULES via LineProcessingService).

Built-ins:
    - Python: uses AST-based docstring stripper.
    - Dart: robust comment stripper for // and /* ... */ with string safety.
    - JS-family and C-like languages: registered lazily using a generic
      C-like stripper that handles // and /* ... */ and preserves strings.

Design goals:
    * Backward compatibility for tests.
    * Reduce reliance on the regex pipeline when a language-aware cleaner
      can be used safely.
"""
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol

from ghconcat.processing.docstrip.py_docstrip import strip_comments_and_docstrings
from ghconcat.processing.docstrip.dart_docstrip import strip_dart_comments
from ghconcat.processing.docstrip.c_like_docstrip import strip_c_like_comments


class CleanerProtocol(Protocol):
    def strip(self, source: str, *, filename: Optional[str] = None) -> str:
        ...


@dataclass(frozen=True)
class _CleanerRegItem:
    cleaner: CleanerProtocol
    priority: int = 0


class LanguageCleaner(CleanerProtocol):
    def __init__(self, fn: Callable[[str, Optional[str]], str]) -> None:
        self._fn = fn

    def strip(self, source: str, *, filename: Optional[str] = None) -> str:
        return self._fn(source, filename)


class LanguageCleanerRegistry:
    def __init__(self) -> None:
        self._by_suffix: Dict[str, _CleanerRegItem] = {}
        self._lazy_builders: Dict[str, tuple[Callable[[], CleanerProtocol], int]] = {}

    @classmethod
    def default(cls) -> 'LanguageCleanerRegistry':
        """Build a default registry with lazy C-like cleaners for many languages."""
        reg = cls()

        # Precise language-specific cleaners
        reg.register('.py', LanguageCleaner(lambda s, fn=None: strip_comments_and_docstrings(s, language='py', filename=fn)), priority=0)
        reg.register('.dart', LanguageCleaner(lambda s, fn=None: strip_dart_comments(s)), priority=0)

        # JS/TS family (existing behavior)
        for suf in ('.js', '.jsx', '.ts', '.tsx'):
            reg.register_lazy(suf, builder=lambda: LanguageCleaner(lambda s, fn=None: strip_c_like_comments(s)), priority=0)

        # Broader C-like set to reduce regex fallback when --rm-comments is used.
        c_like_suffixes = (
            '.c', '.cc', '.cpp', '.cxx', '.h', '.hpp',
            '.java', '.cs', '.go', '.rs',
            '.php', '.swift', '.kt', '.kts', '.scala',
            '.css', '.scss',
        )
        for suf in c_like_suffixes:
            reg.register_lazy(suf, builder=lambda: LanguageCleaner(lambda s, fn=None: strip_c_like_comments(s)), priority=0)

        return reg

    def register(self, suffix: str, cleaner: CleanerProtocol, *, priority: int = 0) -> None:
        sufx = suffix if suffix.startswith('.') else f'.{suffix}'
        key = sufx.lower()
        prev = self._by_suffix.get(key)
        if prev is None or priority >= prev.priority:
            self._by_suffix[key] = _CleanerRegItem(cleaner=cleaner, priority=priority)
        self._lazy_builders.pop(key, None)

    def register_lazy(self, suffix: str, *, builder: Callable[[], CleanerProtocol], priority: int = 0) -> None:
        sufx = suffix if suffix.startswith('.') else f'.{suffix}'
        key = sufx.lower()
        self._lazy_builders[key] = (builder, priority)

    def for_suffix(self, suffix: str) -> Optional[CleanerProtocol]:
        key = (suffix or '').lower()
        item = self._by_suffix.get(key)
        if item:
            return item.cleaner
        lazy = self._lazy_builders.get(key)
        if lazy:
            builder, prio = lazy
            cleaner = builder()
            self.register(key, cleaner, priority=prio)
            return cleaner
        return None