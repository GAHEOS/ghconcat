import html
import logging
import mimetypes
import re
import ssl
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple


class UrlFetcher:
    """Fetch and crawl remote resources with workspace-scoped caching.

    This class encapsulates the URL download (``-f/--url``) and the limited
    crawler (``-F/--url-scrape``) used by *ghconcat*. It mirrors the legacy
    behavior while offering a clean, reusable API for library consumers.

    The implementation preserves:
      • Cache layout under ``<workspace>/.ghconcat_urlcache``.
      • A minimal User-Agent to avoid 403s on stricter servers.
      • TLS behavior controlled by an injected *ssl_ctx_provider* (so the
        CLI-specific env var handling remains in the caller).
      • Suffix filtering semantics consistent with ghconcat v2 flags (-s/-S).
      • Depth-limited BFS crawling restricted by same-host unless disabled.

    Parameters
    ----------
    cache_root:
        The absolute path of the workspace root. The URL cache directory
        will be created as ``cache_root/.ghconcat_urlcache``.
    logger:
        Optional logger instance; if omitted, a module logger is used.
    user_agent:
        HTTP User-Agent header value sent with every request.
    ssl_ctx_provider:
        Callable that returns an :class:`ssl.SSLContext` for a given URL or
        ``None`` to use default verification. This is injected to avoid any
        hard dependency on ghconcat internals and to keep semantics identical
        to the previous implementation (e.g. GHCONCAT_INSECURE_TLS).

    Notes
    -----
    • This class performs no HTML parsing beyond basic ``href="…"`` extraction.
    • Network errors are logged and the offending URL is skipped.
    """

    #: Default header value used to prevent HTTP 403 on some hosts.
    _DEFAULT_UA = "ghconcat/2.0 (+https://gaheos.com)"

    def __init__(
        self,
        cache_root: Path,
        *,
        logger: Optional[logging.Logger] = None,
        user_agent: str = _DEFAULT_UA,
        ssl_ctx_provider: Optional[Callable[[str], Optional[ssl.SSLContext]]] = None,
    ) -> None:
        self._workspace = cache_root
        self._cache_dir = self._workspace / ".ghconcat_urlcache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self._log = logger or logging.getLogger("ghconcat.url_fetcher")
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)

        # Well-known extension sets (kept intentionally broad to mirror legacy behavior)
        self._TEXT_EXT = {
            ".html", ".htm", ".xhtml",
            ".md", ".markdown",
            ".txt", ".text",
            ".css", ".scss", ".less",
            ".js", ".mjs", ".ts", ".tsx", ".jsx",
            ".json", ".jsonc", ".yaml", ".yml",
            ".xml", ".svg",
            ".csv", ".tsv",
            ".py", ".rb", ".php", ".pl", ".pm",
            ".go", ".rs", ".java", ".c", ".cpp", ".cc", ".h", ".hpp",
            ".sh", ".bash", ".zsh", ".ps1",
            ".r", ".lua",
        }
        self._BINARY_EXT = {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".avif",
            ".mp4", ".m4v", ".mov", ".webm", ".ogv", ".flv",
            ".mp3", ".ogg", ".oga", ".wav", ".flac",
            ".woff", ".woff2", ".ttf", ".otf", ".eot",
            ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
            ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
        }
        self._WELL_KNOWN_EXT = self._TEXT_EXT | self._BINARY_EXT

        # Content-Type fallback → extension (legacy-compatible)
        self._MIME_FALLBACK = {
            "text/html": ".html",
            "application/json": ".json",
            "application/javascript": ".js",
            "text/css": ".css",
            "text/plain": ".txt",
            "text/xml": ".xml",
        }

        # Simple patterns reused during scraping
        self._href_re = re.compile(r'href=["\']?([^"\' >]+)', re.I)
        self._ext_re = re.compile(r"\.[A-Za-z0-9_-]{1,8}$")

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        """Download every URL and return the cached file paths.

        Behavior
        --------
        • Filenames are preserved when present; otherwise ``remote_<idx>``.
        • When no extension is present, infer from Content-Type; fall back to
          ``mimetypes.guess_extension`` or ``.html``.
        • Each downloaded file is saved under the cache directory with a
          prefix for stability: ``<idx>_<name>``.

        Parameters
        ----------
        urls:
            Sequence of absolute URLs to download.

        Returns
        -------
        List[Path]
            Paths to the cached files in download order (skipping failures).
        """
        out: List[Path] = []
        for idx, link in enumerate(urls):
            try:
                req = urllib.request.Request(link, headers={"User-Agent": self._ua})
                ctx = self._ssl_ctx_for(link)
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    data = resp.read()
                    ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()

                raw_name = Path(urllib.parse.urlparse(link).path).name or f"remote_{idx}"
                if "." not in raw_name:
                    # Infer extension based on Content-Type
                    ext = (
                        self._MIME_FALLBACK.get(ctype)
                        or mimetypes.guess_extension(ctype)
                        or ".html"
                    )
                    raw_name += ext

                dst = self._cache_dir / f"{idx}_{raw_name}"
                dst.write_bytes(data)
                out.append(dst)
                self._log.info("✔ fetched %s → %s", link, dst)
            except Exception as exc:  # noqa: BLE001
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
        """Breadth-first crawl starting from *seeds*, honoring suffix filters.

        BFS Rules
        ---------
        • Depth ``0`` downloads only the seed(s) themselves.
        • By default remains confined to the original scheme+host; pass
          ``same_host_only=False`` to allow cross-domain traversal.
        • Pre-download filtering:
            - If the URL has a well-known extension, apply include/exclude.
            - If the URL lacks an extension, it is *tentatively allowed* so that
              MIME-based inference can decide after download (legacy behavior).
        • Post-download filtering:
            - If the response is binary and its extension is not included, the
              file is deleted and skipped.

        Parameters
        ----------
        seeds:
            Starting URLs for the crawl.
        suffixes:
            Include-list of extensions as specified by ``-s`` (each item may be
            with or without the leading dot).
        exclude_suf:
            Exclude-list of extensions as specified by ``-S``.
        max_depth:
            Maximum recursion depth (root = 0).
        same_host_only:
            If ``True``, restricts new links to the seed's scheme+host.

        Returns
        -------
        List[Path]
            Ordered list of cached files discovered during the crawl.
        """
        include_set = {s if s.startswith(".") else f".{s}" for s in suffixes}
        exclude_set = {s if s.startswith(".") else f".{s}" for s in exclude_suf} - include_set

        visited: set[str] = set()
        queue = deque[(str, int)]((u, 0) for u in seeds)
        out_paths: List[Path] = []

        def _extract_ext(url: str) -> str:
            m = self._ext_re.search(urllib.parse.urlparse(url).path)
            return m.group(0).lower() if m else ""

        def _is_binary_mime(ctype: str) -> bool:
            if not ctype:
                return False
            if ctype.startswith("text/") or ctype.endswith(("+xml", "+json", "+html")):
                return False
            if ctype in ("application/json", "application/javascript", "application/xml"):
                return False
            return True

        def _skip_pre_download(ext: str) -> bool:
            # Preserve historical semantics:
            # - If ext is known, apply include/exclude now.
            # - If ext unknown, allow download so that MIME can be used later.
            if ext in self._WELL_KNOWN_EXT:
                if include_set and ext not in include_set:
                    return True
                if ext in exclude_set:
                    return True
                return False
            if ext in exclude_set:
                return True
            if include_set and ext not in include_set:
                return False
            return False

        def _download(url: str, idx: int, depth: int) -> Optional[Tuple[Path, str, bytes]]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self._ua})
                ctx = self._ssl_ctx_for(url)
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    data = resp.read()
                    ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()

                name = Path(urllib.parse.urlparse(url).path).name or f"remote_{idx}"
                ext = _extract_ext(name)
                if (not ext) or (ext not in self._WELL_KNOWN_EXT):
                    # Try to infer a better extension from MIME or include-set hints
                    ext = (ext if ext in include_set else "") or self._MIME_FALLBACK.get(ctype) or ".html"
                    if not name.lower().endswith(ext):
                        name += ext

                dst = self._cache_dir / f"scr_{idx}_{name}"
                dst.write_bytes(data)
                self._log.info("✔ scraped %s (d=%d) → %s", url, depth, dst)
                return dst, ctype, data
            except Exception as exc:  # noqa: BLE001
                self._log.error("⚠  could not scrape %s: %s", url, exc)
                return None

        while queue:
            url, depth = queue.popleft()
            if url in visited or depth > max_depth:
                continue
            visited.add(url)

            ext = _extract_ext(url)
            if _skip_pre_download(ext):
                continue

            dl = _download(url, len(visited), depth)
            if dl is None:
                continue
            dst, ctype, body = dl

            if _is_binary_mime(ctype) and dst.suffix.lower() not in include_set:
                try:
                    dst.unlink(missing_ok=True)
                except Exception:
                    pass
                continue

            out_paths.append(dst)

            if ctype.startswith("text/html") and depth < max_depth:
                try:
                    html_txt = body.decode("utf-8", "ignore")
                    for link in self._href_re.findall(html_txt):
                        abs_url = urllib.parse.urljoin(url, html.unescape(link))
                        if same_host_only:
                            if urllib.parse.urlparse(abs_url)[:2] != urllib.parse.urlparse(url)[:2]:
                                continue
                        if abs_url in visited:
                            continue
                        if _skip_pre_download(_extract_ext(abs_url)):
                            continue
                        queue.append((abs_url, depth + 1))
                except Exception:
                    # HTML parse is best-effort; ignore failures.
                    pass

        return out_paths