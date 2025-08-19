"""
Factory for the Git repository manager used by ghconcat.

This module **does not** implement the real Git manager; it only provides
the default factory that wraps an existing project builder (class or callable).
"""

from pathlib import Path
from typing import Callable

from ghconcat.core.interfaces.git import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
)


class DefaultGitManagerFactory(GitManagerFactoryProtocol):
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