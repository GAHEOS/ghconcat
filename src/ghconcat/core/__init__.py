"""
ghconcat.core – Stable DI contracts (Protocols & factories).

This module provides a flat, unified import surface for core Protocols and
default factories, avoiding layered re-exports and keeping consistency with
the rest of the codebase.
"""

from ghconcat.core.interfaces.git import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
)
from ghconcat.discovery.git_manager import DefaultGitManagerFactory

from ghconcat.core.interfaces.net import (
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
)
from ghconcat.discovery.url_fetcher import DefaultUrlFetcherFactory

from ghconcat.core.interfaces.factories import (
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
)

from ghconcat.rendering.factories import (
    DefaultWalkerFactory,
    DefaultRendererFactory,
    DefaultPathResolverFactory,
)

__all__ = [
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "DefaultGitManagerFactory",
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "DefaultUrlFetcherFactory",
    "WalkerFactoryProtocol",
    "RendererFactoryProtocol",
    "PathResolverFactoryProtocol",
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
]