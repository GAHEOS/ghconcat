"""
Cache interfaces for ghconcat.

This module defines a DI-friendly protocol for cache managers used across
the application. It standardizes the surface currently implemented by
`ghconcat.io.cache_manager.CacheManager` without changing runtime behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, Sequence


class CacheManagerProtocol(Protocol):
    """Contract for cache purging implementations.

    Implementations are expected to be best-effort (never raising on delete
    failures) and to log informative messages.
    """

    def purge_all(
        self,
        workspaces: Iterable[Path],
        *,
        patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache"),
    ) -> None:
        """Delete known caches for each workspace directory present in *workspaces*."""

    def purge_in(
        self,
        workspace: Path,
        *,
        patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache"),
    ) -> int:
        """Delete cache directories under *workspace* and return the number of
        cache directories that existed and were attempted to delete."""