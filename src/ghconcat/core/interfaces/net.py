from pathlib import Path
from typing import List, Protocol, Sequence, runtime_checkable

from ghconcat.core.models import FetchRequest, FetchResponse


class HTTPTransportProtocol(Protocol):
    """Minimal HTTP transport abstraction."""

    def request(self, req: FetchRequest) -> FetchResponse: ...


@runtime_checkable
class UrlFetcherProtocol(Protocol):
    """URL fetcher capable of fetching single URLs or scraping with BFS."""

    def fetch(self, urls: Sequence[str]) -> List[Path]: ...
    def scrape(
        self,
        seeds: Sequence[str],
        *,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]: ...


class UrlFetcherFactoryProtocol(Protocol):
    """Factory to build a `UrlFetcherProtocol` bound to a workspace root."""

    def __call__(self, workspace: Path) -> UrlFetcherProtocol: ...