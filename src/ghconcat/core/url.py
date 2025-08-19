"""
core.url – URL fetcher Protocols & default factory for ghconcat.

This module centralizes URL contracts under the `ghconcat.core` namespace.
It re-exports the canonical Protocols from `core.interfaces.net` and the
default factory implementation from the discovery module.
"""

from ghconcat.core.interfaces.net import (
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
)
from ghconcat.discovery.url_fetcher import DefaultUrlFetcherFactory

__all__ = [
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "DefaultUrlFetcherFactory",
]