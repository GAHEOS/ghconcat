from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, Sequence


class CacheManagerProtocol(Protocol):
    """Cache manager interface for purging filesystem caches."""

    def purge_all(
        self, workspaces: Iterable[Path], *, patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache")
    ) -> None: ...

    def purge_in(
        self, workspace: Path, *, patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache")
    ) -> int: ...