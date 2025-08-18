"""
ghconcat.core – Stable DI contracts (Protocols & factories).

This package centralizes thin, dependency-free interfaces that higher-level
components depend on. It intentionally re-exports protocol/factory artifacts
from the canonical modules to avoid behavioral drift while clarifying the
architectural boundaries:

    • ghconcat.core.git  → Git-related Protocols & default factory
    • ghconcat.core.url  → URL-related Protocols & default factory

Rationale
---------
Keeping the canonical definitions in one place prevents cyclic imports and
makes contracts discoverable for both library users and test doubles.
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

__all__ = [
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "DefaultGitManagerFactory",
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "DefaultUrlFetcherFactory",
]