"""
adapters.url – Adapter to expose a concrete URL fetcher via the Protocol.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..core import UrlFetcherProtocol
from ghconcat.discovery.url_fetcher import UrlFetcher


@dataclass
class UrlFetcherAdapter(UrlFetcherProtocol):
    """Adapter that fulfills UrlFetcherProtocol by delegation.

    The adapter wraps :class:`UrlFetcher` (concrete implementation) and forwards
    calls 1:1, preserving the testing seam at the boundary.
    """

    target: UrlFetcher

    def fetch(self, urls: List[str]) -> List[Path]:  # type: ignore[override]
        """Delegate to the wrapped UrlFetcher."""
        return self.target.fetch(urls)

    def scrape(  # type: ignore[override]
        self,
        seeds: List[str],
        *,
        suffixes: List[str],
        exclude_suf: List[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]:
        """Delegate to the wrapped UrlFetcher."""
        return self.target.scrape(
            seeds,
            suffixes=suffixes,
            exclude_suf=exclude_suf,
            max_depth=max_depth,
            same_host_only=same_host_only,
        )