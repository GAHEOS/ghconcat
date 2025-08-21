from __future__ import annotations

"""HTTP transport implementation using urllib.

The transport is intentionally minimal and synchronous. It supports:
- Custom User-Agent via constructor.
- Optional SSL context provider callback per request URL.
"""

import ssl
import urllib.request
from typing import Callable, Optional

from ghconcat.core.interfaces.net import HTTPTransportProtocol
from ghconcat.core.models import FetchRequest, FetchResponse


class UrllibHTTPTransport(HTTPTransportProtocol):
    """urllib-based HTTP transport that satisfies HTTPTransportProtocol."""

    def __init__(self, *, user_agent: Optional[str] = None, ssl_ctx_provider: Optional[Callable[[str], Optional[ssl.SSLContext]]] = None) -> None:
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)

    def request(self, req: FetchRequest) -> FetchResponse:
        """Perform an HTTP request and return a FetchResponse."""
        headers = dict(req.headers or {})
        if self._ua and "User-Agent" not in headers:
            headers["User-Agent"] = self._ua

        url_req = urllib.request.Request(req.url, data=req.body, headers=headers, method=req.method or "GET")
        timeout = float(req.timeout) if req.timeout is not None else 30.0
        ctx = self._ssl_ctx_for(req.url)

        with urllib.request.urlopen(url_req, timeout=timeout, context=ctx) as resp:  # nosec B310 (intended usage)
            body = resp.read()
            status = getattr(resp, "status", None) or int(resp.getcode())
            headers_map = dict(resp.headers.items())
            final_url = resp.geturl()

        return FetchResponse(status=status, headers=headers_map, body=body, final_url=final_url)