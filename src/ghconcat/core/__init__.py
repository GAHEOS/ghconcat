from ghconcat.core.interfaces.git import GitRepositoryManagerProtocol, GitManagerFactoryProtocol
from ghconcat.core.interfaces.net import UrlFetcherProtocol, UrlFetcherFactoryProtocol
from ghconcat.core.interfaces.factories import WalkerFactoryProtocol, RendererFactoryProtocol, PathResolverFactoryProtocol

# Centralized default factories (aliases to the concrete implementations)
from ghconcat.runtime.factories import (
    DefaultWalkerFactory,
    DefaultRendererFactory,
    DefaultPathResolverFactory,
    DefaultGitManagerFactory,
    DefaultUrlFetcherFactory,
)

__all__ = [
    'GitRepositoryManagerProtocol',
    'GitManagerFactoryProtocol',
    'DefaultGitManagerFactory',
    'UrlFetcherProtocol',
    'UrlFetcherFactoryProtocol',
    'DefaultUrlFetcherFactory',
    'WalkerFactoryProtocol',
    'RendererFactoryProtocol',
    'PathResolverFactoryProtocol',
    'DefaultWalkerFactory',
    'DefaultRendererFactory',
    'DefaultPathResolverFactory',
]