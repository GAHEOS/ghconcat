from pathlib import Path
from typing import List, Protocol, Sequence, runtime_checkable

from ghconcat.core.models import FetchRequest, FetchResponse


class HTTPTransportProtocol(Protocol):
    """Thin HTTP transport abstraction to enable custom implementations."""

    def request(self, req: FetchRequest) -> FetchResponse:
        """Perform a HTTP request and return a response object."""
        ...


@runtime_checkable
class UrlFetcherProtocol(Protocol):
    """High-level URL fetcher that can download and scrape content."""

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        """Download a list of URLs into workspace cache, returning local paths."""
        ...

    def scrape(
        self,
        seeds: Sequence[str],
        *,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]:
        """Breadth-first scrape following links, saving matched documents."""
        ...


class UrlFetcherFactoryProtocol(Protocol):
    """Callable factory that builds a `UrlFetcherProtocol` bound to a workspace."""

    def __call__(self, workspace: Path) -> UrlFetcherProtocol:
        ...