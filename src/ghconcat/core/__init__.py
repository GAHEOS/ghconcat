from __future__ import annotations

"""Public surface for ghconcat.core.

This module exposes protocol types and default factory entry-points for
downstream consumers. The intent is to provide a stable import location:

    from ghconcat.core import DefaultWalkerFactory, DefaultRendererFactory, ...

Refactor note:
    - DefaultWalkerFactory, DefaultRendererFactory and DefaultPathResolverFactory
      are now aliased directly from their implementation module
      (ghconcat.rendering.factories) to remove an extra re-export hop.
    - DefaultGitManagerFactory and DefaultUrlFetcherFactory remain sourced from
      ghconcat.runtime.factories, which provides lightweight function factories.

Backwards compatibility:
    Public names and import paths remain unchanged.
"""

# Protocols re-export
from ghconcat.core.interfaces.git import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
)
from ghconcat.core.interfaces.net import (
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
)
from ghconcat.core.interfaces.factories import (
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
)

# Default factories (direct aliases from implementation)
from ghconcat.rendering.factories import (  # noqa: F401
    DefaultWalkerFactory,
    DefaultRendererFactory,
    DefaultPathResolverFactory,
)

# Trivial factories kept in runtime.factories (public API preserved)
from ghconcat.runtime.factories import (  # noqa: F401
    DefaultGitManagerFactory,
    DefaultUrlFetcherFactory,
)

__all__ = [
    # Protocols
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "WalkerFactoryProtocol",
    "RendererFactoryProtocol",
    "PathResolverFactoryProtocol",
    # Default factories
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
    "DefaultGitManagerFactory",
    "DefaultUrlFetcherFactory",
]