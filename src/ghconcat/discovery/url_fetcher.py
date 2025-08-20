import html
import logging
import mimetypes
import re
from collections import deque
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from ghconcat.core.interfaces.net import UrlFetcherProtocol, UrlFetcherFactoryProtocol, HTTPTransportProtocol
from ghconcat.core.models import FetchRequest
from ghconcat.net.urllib_transport import UrllibHTTPTransport
from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed


class UrlFetcher:
    _DEFAULT_UA = 'ghconcat/2.0 (+https://gaheos.com)'

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
        self._cache_dir = self._workspace / '.ghconcat_urlcache'
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger or logging.getLogger('ghconcat.url_fetcher')
        self._ua = user_agent
        self._ssl_ctx_for = ssl_ctx_provider or (lambda _url: None)
        self._http: HTTPTransportProtocol = transport or UrllibHTTPTransport(
            user_agent=self._ua, ssl_ctx_provider=self._ssl_ctx_for
        )

        self._TEXT_EXT = {
            '.html', '.htm', '.xhtml', '.md', '.markdown', '.txt', '.text', '.css', '.scss', '.less', '.js', '.mjs',
            '.ts', '.tsx', '.jsx', '.json', '.jsonc', '.yaml', '.yml', '.xml', '.svg', '.csv', '.tsv', '.py', '.rb',
            '.php', '.pl', '.pm', '.go', '.rs', '.java', '.c', '.cpp', '.cc', '.h', '.hpp', '.sh', '.bash', '.zsh',
            '.ps1', '.r', '.lua'
        }
        self._BINARY_EXT = {
            '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tiff', '.avif',
            '.mp4', '.m4v', '.mov', '.webm', '.ogv', '.flv',
            '.mp3', '.ogg', '.oga', '.wav', '.flac',
            '.woff', '.woff2', '.ttf', '.otf', '.eot',
            '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
            '.zip', '.tar', '.gz', '.tgz', '.bz2', '.xz', '.7z'
        }
        self._WELL_KNOWN_EXT = self._TEXT_EXT | self._BINARY_EXT
        self._MIME_FALLBACK = {
            'text/html': '.html',
            'application/json': '.json',
            'application/javascript': '.js',
            'text/css': '.css',
            'text/plain': '.txt',
            'text/xml': '.xml',
        }
        self._href_re = re.compile(r'href=["\\\']?([^"\\\' >]+)', re.I)
        self._ext_re = re.compile(r'\.[A-Za-z0-9_-]{1,8}$')

    def _http_get(self, url: str, *, timeout: float = 30.0) -> tuple[bytes, str, str]:
        resp = self._http.request(FetchRequest(method='GET', url=url, headers={'User-Agent': self._ua}, timeout=timeout))
        ctype = (resp.headers.get('Content-Type', '') or '').split(';', 1)[0].strip()
        return (resp.body, ctype, resp.final_url)

    def _extract_ext_from_url_path(self, url_path: str) -> str:
        m = self._ext_re.search(url_path)
        return m.group(0).lower() if m else ''

    def _is_binary_mime(self, ctype: str) -> bool:
        """Heuristic to decide if a MIME type is binary for scraping filters."""
        if not ctype:
            return False
        if ctype.startswith('text/') or ctype.endswith(('+xml', '+json', '+html')):
            return False
        if ctype in ('application/json', 'application/javascript', 'application/xml'):
            return False
        return True

    def _infer_extension(self, ctype: str, url_path: str, *, default: str = '.html') -> str:
        """Infer a reasonable extension from MIME type or URL path."""
        # First try explicit mapping, then stdlib guess, then default.
        if ctype in self._MIME_FALLBACK:
            return self._MIME_FALLBACK[ctype]
        guessed = mimetypes.guess_extension(ctype or '')
        if guessed:
            return guessed
        # If the path already has a known extension, keep it as-is.
        ext = self._extract_ext_from_url_path(url_path)
        if ext:
            return ext
        return default

    def _decide_local_name(self, url: str, idx: int, ctype: str, *, mode: str) -> str:
        """Return a stable local filename for a fetched/scraped resource.

        Args:
            url: Source URL.
            idx: Sequence index to ensure uniqueness.
            ctype: Response content type.
            mode: 'fetch' for single URL fetch, 'scrape' for crawler mode.
        """
        from urllib.parse import urlparse

        name = Path(urlparse(url).path).name or f'remote_{idx}'
        url_ext = self._extract_ext_from_url_path(name)

        if mode == 'fetch':
            # Keep as-is if an extension is present; otherwise infer.
            if '.' not in name:
                name += self._infer_extension(ctype, name, default='.html')
            return name

        # SCRAPE mode: normalize to a well-known extension when missing/unknown.
        if not url_ext or url_ext not in self._WELL_KNOWN_EXT:
            inferred = self._infer_extension(ctype, name, default='.html')
            if not name.lower().endswith(inferred):
                name += inferred
        return name

    # Backward-compatible wrappers (used internally).
    def _decide_name_for_fetch(self, url: str, idx: int, ctype: str) -> str:
        return self._decide_local_name(url, idx, ctype, mode='fetch')

    def _decide_name_for_scrape(self, url: str, idx: int, ctype: str) -> str:
        return self._decide_local_name(url, idx, ctype, mode='scrape')

    def fetch(self, urls: Sequence[str]) -> List[Path]:
        out: List[Path] = []
        for idx, link in enumerate(urls):
            try:
                body, ctype, _final_url = self._http_get(link)
                name = self._decide_name_for_fetch(link, idx, ctype)
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
        from urllib.parse import urljoin, urlparse

        include_set, exclude_set = compute_suffix_filters(suffixes, exclude_suf)
        visited: set[str] = set()
        queue = deque(((u, 0) for u in seeds))
        out_paths: List[Path] = []

        def _pre_download_skip(url: str) -> bool:
            url_ext = self._extract_ext_from_url_path(urlparse(url).path)
            if url_ext in self._WELL_KNOWN_EXT:
                return not is_suffix_allowed(f'f{url_ext}', include_set, exclude_set)
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
                self._log.error('⚠  could not scrape %s: %s', url, exc)
                continue

            name = self._decide_name_for_scrape(url, len(visited), ctype)
            dst = self._cache_dir / f'scr_{len(visited)}_{name}'
            try:
                dst.write_bytes(body)
                self._log.info('✔ scraped %s (d=%d) → %s', url, depth, dst)
            except Exception as exc:
                self._log.error('⚠  could not save %s: %s', url, exc)
                continue

            if self._is_binary_mime(ctype):
                # Drop binary files that do not match suffix filters.
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
                    base_host = urlparse(url)
                    for link in self._href_re.findall(html_txt):
                        abs_url = urljoin(url, html.unescape(link))
                        if same_host_only and urlparse(abs_url)[:2] != base_host[:2]:
                            continue
                        if abs_url in visited or _pre_download_skip(abs_url):
                            continue
                        queue.append((abs_url, depth + 1))
                except Exception:
                    # Be resilient to parsing edge cases.
                    pass
        return out_paths


class DefaultUrlFetcherFactory(UrlFetcherFactoryProtocol):
    def __init__(self, builder: Callable[[Path], UrlFetcherProtocol]) -> None:
        self._builder = builder

    def __call__(self, workspace: Path) -> UrlFetcherProtocol:
        return self._builder(workspace)