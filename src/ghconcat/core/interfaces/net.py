from __future__ import annotations
from pathlib import Path
from typing import List, Protocol, Sequence, runtime_checkable, Optional, Callable

from ghconcat.core.models import FetchRequest, FetchResponse


@runtime_checkable
class HTTPTransportProtocol(Protocol):
    def request(self, req: FetchRequest) -> FetchResponse:
        ...


@runtime_checkable
class UrlFetcherProtocol(Protocol):
    def fetch(self, urls: Sequence[str]) -> List[Path]:
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
        ...


@runtime_checkable
class UrlFetcherFactoryProtocol(Protocol):
    def __call__(self, workspace: Path) -> UrlFetcherProtocol:
        ...


@runtime_checkable
class UrlAcceptPolicyProtocol(Protocol):
    """Policy for URL acceptance, naming and traversal decisions."""

    def decide_local_name(self, url: str, idx: int, content_type: str, *, mode: str) -> str:
        ...

    def allowed_by_suffix(self, url: str, *, include: Sequence[str], exclude: Sequence[str]) -> bool:
        ...

    def allow_follow(self, abs_url: str, *, base_url: str, same_host_only: bool) -> bool:
        ...

    def is_binary_type(self, content_type: str) -> bool:
        ...