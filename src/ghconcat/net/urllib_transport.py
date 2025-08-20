"""
urllib_transport – Default HTTP transport using urllib for ghconcat.

This module implements `HTTPTransportProtocol` using Python's stdlib
`urllib.request`. It is injected by default into UrlFetcher to make
network I/O testable and DI-friendly, while preserving existing behavior
(User-Agent, TLS context, timeouts).
"""

from __future__ import annotations

import ssl
import urllib.request
from typing import Callable, Optional

from ghconcat.core.interfaces.net import HTTPTransportProtocol
from ghconcat.core.models import FetchRequest, FetchResponse


class UrllibHTTPTransport(HTTPTransportProtocol):
    """HTTP transport backed by urllib.request.

    Parameters
    ----------
    user_agent:
        Optional fallback UA header to inject when the request headers do not
        already provide one.
    ssl_ctx_provider:
        Optional callable that returns an `ssl.SSLContext` for a given URL.
        When provided, it is used to configure TLS (e.g., insecure mode).
    """

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        ssl_ctx_provider: Optional[Callable[[str], Optional[ssl.SSLContext]]] = None,
    ) -> None:
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)

    def request(self, req: FetchRequest) -> FetchResponse:  # type: ignore[override]
        """Perform a single HTTP request with urllib and return a response."""
        headers = dict(req.headers or {})
        if self._ua and "User-Agent" not in headers:
            headers["User-Agent"] = self._ua

        url_req = urllib.request.Request(
            req.url,
            data=req.body,
            headers=headers,
            method=req.method or "GET",
        )
        timeout = float(req.timeout) if req.timeout is not None else 30.0
        ctx = self._ssl_ctx_for(req.url)

        with urllib.request.urlopen(url_req, timeout=timeout, context=ctx) as resp:
            body = resp.read()
            # Some handlers expose `.status`, others only `getcode()`
            status = getattr(resp, "status", None) or int(resp.getcode())
            headers_map = dict(resp.headers.items())  # case-insensitive mapping
            final_url = resp.geturl()

        return FetchResponse(
            status=status,
            headers=headers_map,
            body=body,
            final_url=final_url,
        )