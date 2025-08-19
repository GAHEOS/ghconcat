# src/ghconcat/core/__init__.py
"""
ghconcat.core – Stable DI contracts (Protocols & factories).

This package centralizes thin, dependency-free interfaces that higher-level
components depend on. It intentionally re-exports protocol/factory artifacts
from the canonical modules to avoid behavioral drift while clarifying the
architectural boundaries:

    • ghconcat.core.git  → Git-related Protocols & default factory
    • ghconcat.core.url  → URL-related Protocols & default factory
    • ghconcat.core.interfaces.* → Canonical Protocols
    • ghconcat.rendering.factories → Default factories (Walker/Renderer/PathResolver)
"""

from .git import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
    DefaultGitManagerFactory,
)
from .url import (
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
    DefaultUrlFetcherFactory,
)

# New DI factory protocols
from ghconcat.core.interfaces.factories import (
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
)

# Default factories for rendering/path resolver
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
    # New DI artifacts
    "WalkerFactoryProtocol",
    "RendererFactoryProtocol",
    "PathResolverFactoryProtocol",
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
]