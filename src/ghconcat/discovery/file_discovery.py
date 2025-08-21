from __future__ import annotations
"""
File discovery orchestration.

Encapsulates local filesystem traversal, git collection and URL fetching/scraping.
The implementation preserves current behavior while improving readability and
type annotations.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ghconcat.core import GitManagerFactoryProtocol, UrlFetcherFactoryProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.rendering.path_resolver import DefaultPathResolver
from ghconcat.core.interfaces.fs import FileDiscoveryProtocol, PathResolverProtocol
from ghconcat.logging.helpers import get_logger


@dataclass
class FileDiscovery(FileDiscoveryProtocol):
    walker: WalkerProtocol
    git_manager_factory: GitManagerFactoryProtocol
    url_fetcher_factory: UrlFetcherFactoryProtocol
    resolver: PathResolverProtocol | None = None
    logger: Optional[logging.Logger] = None

    def _resolve_many(self, base: Path, items: Optional[List[str]]) -> List[Path]:
        if not items:
            return []
        res = self.resolver or DefaultPathResolver()
        return [res.resolve(base, it) for it in items]

    def gather_local(
        self,
        *,
        add_paths: List[str] | None,
        exclude_paths: List[str] | None,
        suffixes: List[str],
        exclude_suf: List[str],
        root: Path,
    ) -> List[Path]:
        if not add_paths:
            return []
        add = self._resolve_many(root, add_paths)
        excl = self._resolve_many(root, exclude_paths)
        return self.walker.gather_files(add, excl, suffixes, exclude_suf)

    def collect_git(
        self,
        *,
        git_specs: List[str] | None,
        git_exclude: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        if not git_specs:
            return []
        mgr = self.git_manager_factory(workspace)
        try:
            return mgr.collect_files(git_specs, git_exclude or [], suffixes, exclude_suf)
        except Exception as exc:
            (self.logger or get_logger('discovery')).error('⚠  git collection failed: %s', exc)
            return []

    def fetch_urls(self, *, urls: List[str] | None, workspace: Path) -> List[Path]:
        if not urls:
            return []
        fetcher = self.url_fetcher_factory(workspace)
        return fetcher.fetch(urls)

    def scrape_urls(
        self,
        *,
        seeds: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]:
        if not seeds:
            return []
        fetcher = self.url_fetcher_factory(workspace)
        return fetcher.scrape(
            seeds,
            suffixes=suffixes,
            exclude_suf=exclude_suf,
            max_depth=max_depth,
            same_host_only=same_host_only,
        )