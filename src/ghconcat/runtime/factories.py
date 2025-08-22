from __future__ import annotations
"""
Centralized re-exports for default factory classes.

This module provides a single, canonical place to import the default
factories used by the runtime. It keeps backward compatibility by
defining or aliasing the existing implementations, while also inlining
trivial factories to reduce file count and maintenance surface.
"""

from pathlib import Path
from typing import Callable

from ghconcat.rendering.factories import (
    DefaultWalkerFactory as _DefaultWalkerFactory,
    DefaultRendererFactory as _DefaultRendererFactory,
    DefaultPathResolverFactory as _DefaultPathResolverFactory,
)
from ghconcat.discovery.url_fetcher import (
    DefaultUrlFetcherFactory as _DefaultUrlFetcherFactory,
)
from ghconcat.core.interfaces.git import (
    GitManagerFactoryProtocol,
    GitRepositoryManagerProtocol,
)


class DefaultGitManagerFactory(GitManagerFactoryProtocol):
    """Thin DI factory for GitRepositoryManagerProtocol builders.

    This class mirrors the previous implementation that lived under
    `ghconcat.discovery.git_manager`. Bringing it here removes one
    trivial module without changing the public API. Tests and external
    imports continue to access it via:

        - ghconcat.runtime.factories.DefaultGitManagerFactory
        - ghconcat.core.DefaultGitManagerFactory  (re-export)
    """

    def __init__(self, builder: Callable[[Path], GitRepositoryManagerProtocol]) -> None:
        self._builder = builder

    def __call__(self, workspace: Path) -> GitRepositoryManagerProtocol:
        return self._builder(workspace)


# Re-exports keeping the public surface identical to before
DefaultWalkerFactory = _DefaultWalkerFactory
DefaultRendererFactory = _DefaultRendererFactory
DefaultPathResolverFactory = _DefaultPathResolverFactory
DefaultUrlFetcherFactory = _DefaultUrlFetcherFactory

__all__ = [
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
    "DefaultGitManagerFactory",
    "DefaultUrlFetcherFactory",
]