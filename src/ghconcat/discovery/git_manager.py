"""
Interfaces and factory for the Git repository manager used by ghconcat.

This module **does not** implement the real Git manager; it only declares the
protocols (interfaces) and a default factory that wraps an existing project
builder (class or callable).

Typical usage:
    factory = DefaultGitManagerFactory(lambda ws: GitRepositoryManager(ws, ...))
    mgr = factory(workspace_path)
    files = mgr.collect_files(git_specs, git_exclude, suffixes, exclude_suf)
"""

from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Protocol, runtime_checkable


@runtime_checkable
class GitRepositoryManagerProtocol(Protocol):
    """Contract for a Git manager that materializes files from -g/-G specs."""

    def collect_files(
        self,
        git_specs: List[str],
        git_exclude: List[str],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Return local (cached) file paths for the provided specs."""


@runtime_checkable
class GitManagerFactoryProtocol(Protocol):
    """Contract for a factory that creates a Git manager for a workspace."""

    def __call__(self, workspace: Path) -> GitRepositoryManagerProtocol:  # pragma: no cover - interface
        ...


class DefaultGitManagerFactory:
    """
    Default factory that wraps a user-provided *builder*.

    It maintains compatibility with the previous pattern (lambdas).
    """

    def __init__(
        self,
        builder: Callable[[Path], GitRepositoryManagerProtocol],
    ) -> None:
        self._builder = builder

    def __call__(self, workspace: Path) -> GitRepositoryManagerProtocol:
        return self._builder(workspace)