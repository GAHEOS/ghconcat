from __future__ import annotations

"""Centralized re-exports for default factories.

This module provides a single, canonical place to import the default
factories used by the runtime. It keeps backward compatibility by
preserving public names while simplifying trivial factories into plain
callables.

Changes:
    - DefaultGitManagerFactory → lightweight function returning the builder.
    - DefaultUrlFetcherFactory → lightweight function returning the builder.
    - Re-exports for Walker/Renderer/PathResolver factories are kept as-is.

Public API (unchanged names):
    - DefaultWalkerFactory
    - DefaultRendererFactory
    - DefaultPathResolverFactory
    - DefaultGitManagerFactory
    - DefaultUrlFetcherFactory
"""

from pathlib import Path
from typing import Callable

from ghconcat.rendering.factories import (
    DefaultWalkerFactory as _DefaultWalkerFactory,
    DefaultRendererFactory as _DefaultRendererFactory,
    DefaultPathResolverFactory as _DefaultPathResolverFactory,
)

from ghconcat.core.interfaces.git import (
    GitManagerFactoryProtocol,
    GitRepositoryManagerProtocol,
)
from ghconcat.core.interfaces.net import (
    UrlFetcherFactoryProtocol,
    UrlFetcherProtocol,
)


def DefaultGitManagerFactory(
    builder: Callable[[Path], GitRepositoryManagerProtocol]
) -> GitManagerFactoryProtocol:
    """Return a Git manager factory as a simple callable.

    Args:
        builder: A callable that, given a workspace `Path`, returns an
            implementation of `GitRepositoryManagerProtocol`.

    Returns:
        A callable compatible with `GitManagerFactoryProtocol`.
    """
    return builder  # The protocol only requires __call__(workspace) -> manager.


def DefaultUrlFetcherFactory(
    builder: Callable[[Path], UrlFetcherProtocol]
) -> UrlFetcherFactoryProtocol:
    """Return an URL fetcher factory as a simple callable.

    Args:
        builder: A callable that, given a workspace `Path`, returns an
            implementation of `UrlFetcherProtocol`.

    Returns:
        A callable compatible with `UrlFetcherFactoryProtocol`.
    """
    return builder  # The protocol only requires __call__(workspace) -> fetcher.


# Re-export non-trivial factories from rendering.factories
DefaultWalkerFactory = _DefaultWalkerFactory
DefaultRendererFactory = _DefaultRendererFactory
DefaultPathResolverFactory = _DefaultPathResolverFactory

__all__ = [
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
    "DefaultGitManagerFactory",
    "DefaultUrlFetcherFactory",
]