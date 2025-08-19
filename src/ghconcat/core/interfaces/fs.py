from pathlib import Path
from typing import List, Protocol, Sequence


class PathResolverProtocol(Protocol):
    """Resolve and validate project/workspace paths."""
    def resolve(self, base: Path, maybe: str | None) -> Path: ...
    def is_within_workspace(self, path: Path) -> bool: ...
    def workspace_root(self) -> Path | None: ...


class FileDiscoveryProtocol(Protocol):
    """Enumerate files across local paths, Git repositories and URLs."""

    def gather_local(
        self,
        *,
        add_paths: List[str] | None,
        exclude_paths: List[str] | None,
        suffixes: List[str],
        exclude_suf: List[str],
        root: Path,
    ) -> List[Path]: ...

    def collect_git(
        self,
        *,
        git_specs: List[str] | None,
        git_exclude: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]: ...

    def fetch_urls(self, *, urls: List[str] | None, workspace: Path) -> List[Path]: ...

    def scrape_urls(
        self,
        *,
        seeds: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]: ...