from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable, Optional


@runtime_checkable
class PathResolverProtocol(Protocol):
    def resolve(self, base: Path, path: str) -> Path:
        ...

    def is_within_workspace(self, path: Path) -> bool:
        ...

    def set_workspace_root(self, root: Optional[Path]) -> None:
        ...


@runtime_checkable
class FileDiscoveryProtocol(Protocol):
    def gather_local(
            self,
            *,
            add_paths: Sequence[str | Path],
            exclude_paths: Sequence[str | Path] | None,
            suffixes: Sequence[str] | None,
            exclude_suf: Sequence[str] | None,
            root: Path,
    ) -> list[Path]:
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
        ...

    def fetch_urls(self, *, urls: Sequence[str] | None, workspace: Path) -> list[Path]:
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
        ...
