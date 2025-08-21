from __future__ import annotations
"""
URL fetching and lightweight scraping.

This module downloads single URLs (`fetch`) and performs breadth-first crawling
(`scrape`) with basic suffix-based filtering. The content is cached under
`.ghconcat_urlcache` within the given workspace.

Refactor notes:
- Extract acceptance/filenaming rules into UrlAcceptPolicyProtocol.
- Preserve behavior, logging, caching layout and naming scheme.
"""
import html
import logging
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse

from ghconcat.core.interfaces.net import (
    HTTPTransportProtocol,
    UrlAcceptPolicyProtocol,
    UrlFetcherFactoryProtocol,
    UrlFetcherProtocol,
)
from ghconcat.core.models import FetchRequest
from ghconcat.discovery.url_policy import DefaultUrlAcceptPolicy
from ghconcat.logging.helpers import get_logger
from ghconcat.net.urllib_transport import UrllibHTTPTransport
from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed


class UrlFetcher(UrlFetcherProtocol):
    import re as _re
    _HREF_RE = _re.compile(r'href=["\\\']?([^"\\\' >]+)', _re.I)

    def __init__(
        self,
        cache_root: Path,
        *,
        logger: Optional[logging.Logger] = None,
        user_agent: str = 'ghconcat/2.0 (+https://gaheos.com)',
        ssl_ctx_provider: Optional[Callable[[str], Optional[object]]] = None,
        transport: Optional[HTTPTransportProtocol] = None,
        policy: Optional[UrlAcceptPolicyProtocol] = None,
    ) -> None:
        self._workspace = cache_root
        self._cache_dir = self._workspace / '.ghconcat_urlcache'
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger or get_logger('url_fetcher')
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)
        self._http: HTTPTransportProtocol = transport or UrllibHTTPTransport(
            user_agent=self._ua, ssl_ctx_provider=self._ssl_ctx_for
        )
        self._policy: UrlAcceptPolicyProtocol = policy or DefaultUrlAcceptPolicy()

    def _http_get(self, url: str, *, timeout: float = 30.0) -> tuple[bytes, str, str]:
        resp = self._http.request(
            FetchRequest(method='GET', url=url, headers={'User-Agent': self._ua}, timeout=timeout)
        )
        ctype = (resp.headers.get('Content-Type', '') or '').split(';', 1)[0].strip()
        return (resp.body, ctype, resp.final_url)

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        out: List[Path] = []
        for idx, link in enumerate(urls):
            try:
                body, ctype, _final_url = self._http_get(link)
                name = self._policy.decide_local_name(link, idx, ctype, mode='fetch')
                dst = self._cache_dir / f'{idx}_{name}'
                dst.write_bytes(body)
                out.append(dst)
                self._log.info('✔ fetched %s → %s', link, dst)
            except Exception as exc:
                self._log.error('⚠  could not fetch %s: %s', link, exc)
        return out

    def scrape(
        self,
        seeds: Sequence[str],
        *,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
        max_depth: int = 2,
        same_host_only: bool = True,
    ) -> List[Path]:
        include_set, exclude_set = compute_suffix_filters(suffixes, exclude_suf)
        visited: set[str] = set()
        queue = deque(((u, 0) for u in seeds))
        out_paths: List[Path] = []

        def _pre_download_skip(url: str) -> bool:
            return not self._policy.allowed_by_suffix(url, include=include_set, exclude=exclude_set)

        while queue:
            url, depth = queue.popleft()
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            if _pre_download_skip(url):
                continue

            try:
                body, ctype, _final_url = self._http_get(url)
            except Exception as exc:
                self._log.error('⚠  could not scrape %s: %s', url, exc)
                continue

            name = self._policy.decide_local_name(url, len(visited), ctype, mode='scrape')
            dst = self._cache_dir / f'scr_{len(visited)}_{name}'
            try:
                dst.write_bytes(body)
                self._log.info('✔ scraped %s (d=%d) → %s', url, depth, dst)
            except Exception as exc:
                self._log.error('⚠  could not save %s: %s', url, exc)
                continue

            if self._policy.is_binary_type(ctype):
                if not is_suffix_allowed(dst.name, include_set, exclude_set):
                    try:
                        dst.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue

            out_paths.append(dst)

            if ctype.startswith('text/html') and depth < max_depth:
                try:
                    html_txt = body.decode('utf-8', 'ignore')
                    base_url = url
                    base_host = urlparse(url)
                    for link in self._HREF_RE.findall(html_txt):
                        abs_url = urljoin(url, html.unescape(link))
                        if not self._policy.allow_follow(abs_url, base_url=base_url, same_host_only=same_host_only):
                            continue
                        if abs_url in visited or _pre_download_skip(abs_url):
                            continue
                        queue.append((abs_url, depth + 1))
                except Exception:
                    pass

        return out_paths


class DefaultUrlFetcherFactory(UrlFetcherFactoryProtocol):
    def __init__(self, builder):
        self._builder = builder

    def __call__(self, workspace: Path) -> UrlFetcherProtocol:
        return self._builder(workspace)