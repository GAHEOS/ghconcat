from __future__ import annotations
"""LanguageCleanerRegistry

Provide pluggable, language-aware comment/docstring cleaners to decouple
WalkerAppender from per-language conditionals.

This version enhances the registry with **lazy registration**: you can register
a suffix with a builder callback that will be invoked on first access.
If no cleaner exists for a suffix, the walker falls back to the regex-based
pipeline (COMMENT_RULES via LineProcessingService).

Built-ins:
    - Python: uses AST-based docstring stripper.
    - Dart: uses robust comment stripper for // and /* ... */ with string safety.
    - JS-family (js/ts/jsx/tsx): registered lazily using a generic C-like stripper.

Design goals:
    * Backward compatibility for tests.
    * Incremental adoption of language-specific cleaners.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol

from ghconcat.processing.docstrip.py_docstrip import strip_comments_and_docstrings
from ghconcat.processing.docstrip.dart_docstrip import strip_dart_comments
from ghconcat.processing.docstrip.c_like_docstrip import strip_c_like_comments


class CleanerProtocol(Protocol):
    def strip(self, source: str, *, filename: Optional[str] = None) -> str:  # pragma: no cover - protocol
        ...


@dataclass(frozen=True)
class _CleanerRegItem:
    cleaner: CleanerProtocol
    priority: int = 0


class LanguageCleaner(CleanerProtocol):
    """Small adapter to unify function-based strippers under a common protocol."""

    def __init__(self, fn: Callable[[str, Optional[str]], str]) -> None:
        self._fn = fn

    def strip(self, source: str, *, filename: Optional[str] = None) -> str:
        return self._fn(source, filename)


class LanguageCleanerRegistry:
    """Registry that returns a cleaner per suffix, with lazy builders support."""

    def __init__(self) -> None:
        self._by_suffix: Dict[str, _CleanerRegItem] = {}
        self._lazy_builders: Dict[str, tuple[Callable[[], CleanerProtocol], int]] = {}

    @classmethod
    def default(cls) -> "LanguageCleanerRegistry":
        """Bootstrap a default registry with immediate and lazy mappings."""
        reg = cls()

        # Immediate (eager) registrations for guaranteed test behavior.
        reg.register(
            ".py",
            LanguageCleaner(lambda s, fn=None: strip_comments_and_docstrings(s, language="py", filename=fn)),
            priority=0,
        )
        reg.register(".dart", LanguageCleaner(lambda s, fn=None: strip_dart_comments(s)), priority=0)

        # Lazy registrations for families where a single cleaner is enough (C-like).
        for suf in (".js", ".jsx", ".ts", ".tsx"):
            reg.register_lazy(
                suf,
                builder=lambda: LanguageCleaner(lambda s, fn=None: strip_c_like_comments(s)),
                priority=0,
            )

        # (Room for more) e.g., ".go", ".java" could be added lazily as well:
        # for suf in (".go", ".java"):
        #     reg.register_lazy(suf, builder=lambda: LanguageCleaner(lambda s, fn=None: strip_c_like_comments(s)), priority=0)

        return reg

    def register(self, suffix: str, cleaner: CleanerProtocol, *, priority: int = 0) -> None:
        """Register a cleaner immediately for a given suffix."""
        sufx = suffix if suffix.startswith(".") else f".{suffix}"
        key = sufx.lower()
        prev = self._by_suffix.get(key)
        if prev is None or priority >= prev.priority:
            self._by_suffix[key] = _CleanerRegItem(cleaner=cleaner, priority=priority)
        # If we register eagerly, drop any lazy builder for the same suffix.
        self._lazy_builders.pop(key, None)

    def register_lazy(self, suffix: str, *, builder: Callable[[], CleanerProtocol], priority: int = 0) -> None:
        """Register a lazy builder for the suffix; constructed on first use."""
        sufx = suffix if suffix.startswith(".") else f".{suffix}"
        key = sufx.lower()
        self._lazy_builders[key] = (builder, priority)

    def for_suffix(self, suffix: str) -> Optional[CleanerProtocol]:
        """Return a cleaner for the suffix, materializing a lazy builder if needed."""
        key = (suffix or "").lower()
        item = self._by_suffix.get(key)
        if item:
            return item.cleaner

        lazy = self._lazy_builders.get(key)
        if lazy:
            builder, prio = lazy
            cleaner = builder()
            # Cache the materialized cleaner for subsequent calls.
            self.register(key, cleaner, priority=prio)
            return cleaner

        return None