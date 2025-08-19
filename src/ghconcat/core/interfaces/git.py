from pathlib import Path
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class GitRepositoryManagerProtocol(Protocol):
    """Contract for a Git manager that materializes files from -g/-G specs."""

    def collect_files(
        self,
        git_specs: List[str],
        git_exclude: List[str],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]: ...


@runtime_checkable
class GitManagerFactoryProtocol(Protocol):
    """Factory that creates a Git manager bound to a workspace."""

    def __call__(self, workspace: Path) -> GitRepositoryManagerProtocol:  # pragma: no cover - interface
        ...