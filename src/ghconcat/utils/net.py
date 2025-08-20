"""
utils.net – Small, centralized HTTP/TLS utilities for ghconcat.

This module consolidates:
  • DEFAULT_UA                – stable User-Agent used across HTTP requests.
  • ssl_context_for(url)      – GHCONCAT_INSECURE_TLS-aware SSL context builder.
  • read_url(url, ...)        – thin urllib wrapper returning (bytes, content-type).

Design goals
------------
• Avoid code duplication in UrlFetcher (fetch/scrape paths shared a request block).
• Keep behavior strictly identical to the former ad-hoc helpers in cli/url_fetcher.
• Provide tiny, dependency-free primitives that are easy to test and reuse.
"""

from __future__ import annotations

import os
import ssl
import urllib.request
from typing import Callable, Optional, Tuple

DEFAULT_UA: str = "ghconcat/2.0 (+https://gaheos.com)"


def ssl_context_for(url: str) -> Optional[ssl.SSLContext]:
    """Return an SSL context honoring GHCONCAT_INSECURE_TLS for HTTPS URLs.

    Behavior
    --------
    • Only applies to HTTPS URLs.
    • When GHCONCAT_INSECURE_TLS=1, hostname verification and CA checks
      are disabled (handy for CI or brittle sites in non-critical fetches).

    Args:
        url: Absolute URL to be requested.

    Returns:
        An SSLContext instance or None (default verification).
    """
    if not url.lower().startswith("https"):
        return None
    if os.getenv("GHCONCAT_INSECURE_TLS") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def read_url(
    url: str,
    *,
    timeout: float = 30.0,
    user_agent: str = DEFAULT_UA,
    ctx_provider: Optional[Callable[[str], Optional[ssl.SSLContext]]] = None,
) -> Tuple[bytes, str]:
    """Return (body, content_type) for *url* with a minimal header set.

    Notes
    -----
    • This is intentionally tiny and synchronous.
    • Content-Type is returned without charset parameters (e.g. 'text/html').

    Args:
        url: Absolute URL to fetch.
        timeout: Network timeout in seconds.
        user_agent: UA header to include in the request.
        ctx_provider: Optional callable producing an SSL context for *url*.

    Returns:
        A (bytes, str) tuple with the response body and the Content-Type value.
    """
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    ctx = ctx_provider(url) if ctx_provider else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()
    return data, ctype