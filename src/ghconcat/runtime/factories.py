from __future__ import annotations

"""Centralized re-exports for default factory classes.

This module provides a single, canonical place to import the default
factories used by the runtime. It keeps backward compatibility by
aliasing the existing implementations.
"""

from ghconcat.rendering.factories import (
    DefaultWalkerFactory as _DefaultWalkerFactory,
    DefaultRendererFactory as _DefaultRendererFactory,
    DefaultPathResolverFactory as _DefaultPathResolverFactory,
)
from ghconcat.discovery.git_manager import (
    DefaultGitManagerFactory as _DefaultGitManagerFactory,
)
from ghconcat.discovery.url_fetcher import (
    DefaultUrlFetcherFactory as _DefaultUrlFetcherFactory,
)

# Thin aliases – centralized names for the rest of the app.
DefaultWalkerFactory = _DefaultWalkerFactory
DefaultRendererFactory = _DefaultRendererFactory
DefaultPathResolverFactory = _DefaultPathResolverFactory
DefaultGitManagerFactory = _DefaultGitManagerFactory
DefaultUrlFetcherFactory = _DefaultUrlFetcherFactory

__all__ = [
    'DefaultWalkerFactory',
    'DefaultRendererFactory',
    'DefaultPathResolverFactory',
    'DefaultGitManagerFactory',
    'DefaultUrlFetcherFactory',
]