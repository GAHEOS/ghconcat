"""
file_discovery – Unified discovery (local, Git and URLs) for ghconcat.

This module provides:
  • FileDiscoveryProtocol – stable contract for dependency injection and tests.
  • FileDiscovery         – default implementation aggregating local walking,
                            Git repository collection and URL fetching/scraping.

It knows nothing about CLI details; it only collaborates with:
  • WalkerAppender
  • GitManagerFactoryProtocol
  • UrlFetcherFactoryProtocol

Change (2025-08-18)
-------------------
- Inject PathResolverProtocol to centralize path resolution and remove the
  duplication that existed between this module and execution.py. When a
  resolver is not provided, DefaultPathResolver is used on demand.

Compatibility
-------------
- The constructor remains backward-compatible. 'resolver' is optional and a
  sensible default is used if omitted. ExecutionEngine does not require any
  changes.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

from ghconcat.core import GitManagerFactoryProtocol, UrlFetcherFactoryProtocol
from ghconcat.io.walker import WalkerAppender
from ghconcat.rendering.path_resolver import PathResolverProtocol, DefaultPathResolver


@runtime_checkable
class FileDiscoveryProtocol(Protocol):
    """Contract for file discovery across local paths, Git repositories and URLs."""

    def gather_local(
        self,
        *,
        add_paths: List[str] | None,
        exclude_paths: List[str] | None,
        suffixes: List[str],
        exclude_suf: List[str],
        root: Path,
    ) -> List[Path]:
        """Resolve local “-a / -A” paths against *root* and return matching files."""

    def collect_git(
        self,
        *,
        git_specs: List[str] | None,
        git_exclude: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Resolve “-g / -G” specs into cached filesystem paths inside *workspace*."""

    def fetch_urls(self, *, urls: List[str] | None, workspace: Path) -> List[Path]:
        """Download “-f/--url” resources into the workspace-scoped cache directory."""

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
        """Breadth-first crawl from *seeds*, honoring filters and depth limits."""


@dataclass
class FileDiscovery(FileDiscoveryProtocol):
    """Aggregate discovery across local filesystem, Git and remote URLs.

    The resolver is injected to avoid duplicating path normalization rules
    (absolute vs. relative) that already exist in DefaultPathResolver.
    """

    walker: WalkerAppender
    git_manager_factory: GitManagerFactoryProtocol
    url_fetcher_factory: UrlFetcherFactoryProtocol
    resolver: PathResolverProtocol | None = None
    logger: Optional[logging.Logger] = None

    # ---------- Local filesystem ----------

    def _resolve_many(self, base: Path, items: Optional[List[str]]) -> List[Path]:
        """Resolve a list of path-like strings against *base* using the resolver."""
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
        """Resolve -a/-A paths and delegate the walk to WalkerAppender."""
        if not add_paths:
            return []
        add = self._resolve_many(root, add_paths)
        excl = self._resolve_many(root, exclude_paths)
        return self.walker.gather_files(add, excl, suffixes, exclude_suf)

    # ---------- Git repositories ----------

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
            return mgr.collect_files(git_specs, git_exclude or [], suffixes, exclude_suf)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            (self.logger or logging.getLogger("ghconcat.discovery")).error(
                "⚠  git collection failed: %s", exc
            )
            return []

    # ---------- Remote URLs ----------

    def fetch_urls(self, *, urls: List[str] | None, workspace: Path) -> List[Path]:
        if not urls:
            return []
        fetcher = self.url_fetcher_factory(workspace)
        return fetcher.fetch(urls)  # type: ignore[attr-defined]

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
        return fetcher.scrape(  # type: ignore[attr-defined]
            seeds,
            suffixes=suffixes,
            exclude_suf=exclude_suf,
            max_depth=max_depth,
            same_host_only=same_host_only,
        )