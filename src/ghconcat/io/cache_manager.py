"""
Cache manager for ghconcat caches.

This module encapsulates deletion of workspace-scoped caches:
  • .ghconcat_gitcache
  • .ghconcat_urlcache

Having a dedicated class improves testability and avoids duplication
in CLI/engine code.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ghconcat.core.interfaces.cache import CacheManagerProtocol


class CacheManager(CacheManagerProtocol):
    """Purge ghconcat caches in one or multiple workspaces.

    The manager is intentionally small and side-effect free except for
    the actual deletion. It logs informative messages and never raises
    on deletion failures (warnings are emitted instead).
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.cache")

    def purge_all(
        self,
        workspaces: Iterable[Path],
        *,
        patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache"),
    ) -> None:
        """Delete known caches in each workspace directory found in *workspaces*."""
        for ws in workspaces:
            self.purge_in(ws, patterns=patterns)

    def purge_in(
        self,
        workspace: Path,
        *,
        patterns: Sequence[str] = (".ghconcat_gitcache", ".ghconcat_urlcache"),
    ) -> int:
        """Delete cache directories under *workspace*.

        Returns
        -------
        int
            Number of cache directories that existed and were attempted to delete.
        """
        n = 0
        for pat in patterns:
            tgt = Path(workspace) / pat
            if tgt.exists():
                n += 1
                try:
                    shutil.rmtree(tgt, ignore_errors=True)
                    self._log.info("🗑  cache removed → %s", tgt)
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("⚠  could not delete %s: %s", tgt, exc)
        return n