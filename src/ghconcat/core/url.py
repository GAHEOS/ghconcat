"""
core.url – URL fetcher Protocols & default factory for ghconcat.

This module centralizes the URL contracts under the `ghconcat.core` namespace
while preserving the exact runtime classes by re-using the canonical
definitions from the original module. This avoids duplication and guarantees
test compatibility (type identity remains the same).
"""

from __future__ import annotations

from ghconcat.discovery.url_fetcher import (  # reuse canonical definitions
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
    DefaultUrlFetcherFactory,
)

__all__ = [
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "DefaultUrlFetcherFactory",
]