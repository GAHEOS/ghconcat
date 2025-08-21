from __future__ import annotations
import logging
import shutil
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ghconcat.core.interfaces.cache import CacheManagerProtocol
from ghconcat.logging.helpers import get_logger


class CacheManager(CacheManagerProtocol):
    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or get_logger('io.cache')

    def purge_all(self, workspaces: Iterable[Path], *,
                  patterns: Sequence[str] = ('.ghconcat_gitcache', '.ghconcat_urlcache')) -> None:
        for ws in workspaces:
            self.purge_in(ws, patterns=patterns)

    def purge_in(self, workspace: Path, *,
                 patterns: Sequence[str] = ('.ghconcat_gitcache', '.ghconcat_urlcache')) -> int:
        n = 0
        for pat in patterns:
            tgt = Path(workspace) / pat
            if tgt.exists():
                n += 1
                try:
                    shutil.rmtree(tgt, ignore_errors=True)
                    self._log.info('🗑  cache removed → %s', tgt)
                except Exception as exc:
                    self._log.warning('⚠  could not delete %s: %s', tgt, exc)
        return n
