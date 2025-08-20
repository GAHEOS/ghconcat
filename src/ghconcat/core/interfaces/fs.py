from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class PathResolverProtocol(Protocol):
    """Resolves paths relative to a base and optionally enforces a workspace root."""

    def resolve(self, base: Path, path: str) -> Path:
        """Resolve `path` against `base`, normalizing symlinks when applicable."""
        ...

    def is_within_workspace(self, path: Path) -> bool:
        """Return True if `path` is inside the configured workspace root."""
        ...

    def set_workspace_root(self, root: Path) -> None:
        """Hint the resolver about the current workspace root (optional)."""
        ...


@runtime_checkable
class FileDiscoveryProtocol(Protocol):
    """Abstracts discovery across local FS, Git sources and remote URLs."""

    def gather_local(
        self,
        *,
        add_paths: Sequence[str | Path],
        exclude_paths: Sequence[str | Path] | None,
        suffixes: Sequence[str] | None,
        exclude_suf: Sequence[str] | None,
        root: Path,
    ) -> list[Path]:
        """Discover local files from explicit paths and recursive directories."""
        ...

    def collect_git(
        self,
        *,
        git_specs: Sequence[str] | None,
        git_exclude: Sequence[str] | None,
        workspace: Path,
        suffixes: Sequence[str] | None,
        exclude_suf: Sequence[str] | None,
    ) -> list[Path]:
        """Collect files from remote Git specs into the workspace cache."""
        ...

    def fetch_urls(self, *, urls: Sequence[str] | None, workspace: Path) -> list[Path]:
        """Download URLs into a workspace cache and return local paths."""
        ...

    def scrape_urls(
        self,
        *,
        seeds: Sequence[str] | None,
        workspace: Path,
        suffixes: Sequence[str] | None,
        exclude_suf: Sequence[str] | None,
        max_depth: int,
        same_host_only: bool,
    ) -> list[Path]:
        """Breadth‑first scrape starting at `seeds`, honoring suffix filters."""
        ...