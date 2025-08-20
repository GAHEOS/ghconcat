from __future__ import annotations

import html
import logging
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ghconcat.core.interfaces.net import HTTPTransportProtocol, UrlFetcherFactoryProtocol, UrlFetcherProtocol
from ghconcat.core.models import FetchRequest
from ghconcat.net.urllib_transport import UrllibHTTPTransport
from ghconcat.utils.mime import extract_ext_from_url_path, infer_extension, is_binary_mime
from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed


class UrlFetcher(UrlFetcherProtocol):
    """Fetches and optionally scrapes URLs into a workspace-local cache."""

    _DEFAULT_UA = "ghconcat/2.0 (+https://gaheos.com)"

    # Class-level constants to avoid re-allocating sets per instance
    _TEXT_EXT = {
        ".html", ".htm", ".xhtml", ".md", ".markdown", ".txt", ".text",
        ".css", ".scss", ".less", ".js", ".mjs", ".ts", ".tsx", ".jsx",
        ".json", ".jsonc", ".yaml", ".yml", ".xml", ".svg", ".csv", ".tsv",
        ".py", ".rb", ".php", ".pl", ".pm", ".go", ".rs", ".java", ".c",
        ".cpp", ".cc", ".h", ".hpp", ".sh", ".bash", ".zsh", ".ps1", ".r", ".lua",
    }
    _BINARY_EXT = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".avif",
        ".mp4", ".m4v", ".mov", ".webm", ".ogv", ".flv",
        ".mp3", ".ogg", ".oga", ".wav", ".flac",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    }
    _WELL_KNOWN_EXT = _TEXT_EXT | _BINARY_EXT
    _MIME_FALLBACK = {
        "text/html": ".html",
        "application/json": ".json",
        "application/javascript": ".js",
        "text/css": ".css",
        "text/plain": ".txt",
        "text/xml": ".xml",
    }

    # Compiled once per class
    import re as _re
    _HREF_RE = _re.compile(r'href=["\\\']?([^"\\\' >]+)', _re.I)

    def __init__(
        self,
        cache_root: Path,
        *,
        logger: Optional[logging.Logger] = None,
        user_agent: str = _DEFAULT_UA,
        ssl_ctx_provider: Optional[Callable[[str], Optional[object]]] = None,
        transport: Optional[HTTPTransportProtocol] = None,
    ) -> None:
        self._workspace = cache_root
        self._cache_dir = self._workspace / ".ghconcat_urlcache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger or logging.getLogger("ghconcat.url_fetcher")
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)
        self._http: HTTPTransportProtocol = transport or UrllibHTTPTransport(
            user_agent=self._ua, ssl_ctx_provider=self._ssl_ctx_for
        )

    def _http_get(self, url: str, *, timeout: float = 30.0) -> tuple[bytes, str, str]:
        resp = self._http.request(
            FetchRequest(
                method="GET",
                url=url,
                headers={"User-Agent": self._ua},
                timeout=timeout,
            )
        )
        ctype = (resp.headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        return (resp.body, ctype, resp.final_url)

    def _decide_local_name(self, url: str, idx: int, ctype: str, *, mode: str) -> str:
        """Choose a local filename based on URL path and content type.

        Args:
            url: Original URL.
            idx: Sequential index for uniqueness.
            ctype: Response Content-Type.
            mode: 'fetch' for direct downloads or 'scrape' for crawled links.
        """
        from urllib.parse import urlparse

        name = Path(urlparse(url).path).name or f"remote_{idx}"
        url_ext = extract_ext_from_url_path(name)

        if mode == "fetch":
            # Preserve name; ensure there is an extension
            if "." not in name:
                name += infer_extension(ctype, name, default=".html", fallback=self._MIME_FALLBACK)
            return name

        # Scrape mode: normalize unknown extensions
        if not url_ext or url_ext not in self._WELL_KNOWN_EXT:
            inferred = infer_extension(ctype, name, default=".html", fallback=self._MIME_FALLBACK)
            if not name.lower().endswith(inferred):
                name += inferred
        return name

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        """Fetch a list of URLs and persist them into the URL cache directory."""
        out: List[Path] = []
        for idx, link in enumerate(urls):
            try:
                body, ctype, _final_url = self._http_get(link)
                name = self._decide_local_name(link, idx, ctype, mode="fetch")
                dst = self._cache_dir / f"{idx}_{name}"
                dst.write_bytes(body)
                out.append(dst)
                self._log.info("✔ fetched %s → %s", link, dst)
            except Exception as exc:
                self._log.error("⚠  could not fetch %s: %s", link, exc)
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
        """Breadth-first scrape following <a href> links.

        Respects suffix allow/deny lists both before downloading (by extension)
        and after (by content-type).
        """
        from urllib.parse import urljoin, urlparse

        include_set, exclude_set = compute_suffix_filters(suffixes, exclude_suf)
        visited: set[str] = set()
        queue = deque(((u, 0) for u in seeds))
        out_paths: List[Path] = []

        def _pre_download_skip(url: str) -> bool:
            url_ext = extract_ext_from_url_path(urlparse(url).path)
            if url_ext in self._WELL_KNOWN_EXT:
                return not is_suffix_allowed(f"f{url_ext}", include_set, exclude_set)
            return False

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
                self._log.error("⚠  could not scrape %s: %s", url, exc)
                continue

            name = self._decide_local_name(url, len(visited), ctype, mode="scrape")
            dst = self._cache_dir / f"scr_{len(visited)}_{name}"
            try:
                dst.write_bytes(body)
                self._log.info("✔ scraped %s (d=%d) → %s", url, depth, dst)
            except Exception as exc:
                self._log.error("⚠  could not save %s: %s", url, exc)
                continue

            if is_binary_mime(ctype):
                # Enforce suffix filters post-download for binaries
                if not is_suffix_allowed(dst.name, include_set, exclude_set):
                    try:
                        dst.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue

            out_paths.append(dst)

            if ctype.startswith("text/html") and depth < max_depth:
                try:
                    html_txt = body.decode("utf-8", "ignore")
                    base_host = urlparse(url)
                    for link in self._HREF_RE.findall(html_txt):
                        abs_url = urljoin(url, html.unescape(link))
                        if same_host_only and urlparse(abs_url)[:2] != base_host[:2]:
                            continue
                        if abs_url in visited or _pre_download_skip(abs_url):
                            continue
                        queue.append((abs_url, depth + 1))
                except Exception:
                    # Robust against malformed pages
                    pass

        return out_paths


class DefaultUrlFetcherFactory(UrlFetcherFactoryProtocol):
    """Factory with an overridable builder callable."""

    def __init__(self, builder: Callable[[Path], UrlFetcherProtocol]) -> None:
        self._builder = builder

    def __call__(self, workspace: Path) -> UrlFetcherProtocol:
        return self._builder(workspace)