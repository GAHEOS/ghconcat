from pathlib import Path
from typing import List, Protocol, Sequence, runtime_checkable

from ghconcat.core.models import FetchRequest, FetchResponse


class HTTPTransportProtocol(Protocol):
    """Low-level HTTP transport (used for deterministic tests and retries)."""
    def request(self, req: FetchRequest) -> FetchResponse: ...


@runtime_checkable
class UrlFetcherProtocol(Protocol):
    """High-level URL fetcher with caching/decoding policies (workspace-scoped)."""

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        """Download absolute URLs and return cached file paths in order."""

    def scrape(
        self,
        seeds: Sequence[str],
        *,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]:
        """Breadth-first crawl from *seeds* honoring filters and depth limits."""


class UrlFetcherFactoryProtocol(Protocol):
    """Factory that creates a URL fetcher bound to a *workspace* directory."""

    def __call__(self, workspace: Path) -> UrlFetcherProtocol:  # pragma: no cover - interface
        ...