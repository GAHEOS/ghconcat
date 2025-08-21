from __future__ import annotations
"""
Default URL acceptance policy for UrlFetcher.

Encapsulates:
- Local filename decision based on URL path and content type.
- Pre-download suffix filtering for known extensions.
- Link-follow rules (same-host constraints).
- Binary vs text MIME decision.

NOTE:
    MIME fallback mapping is centralized in `ghconcat.utils.mime`.
"""

from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from ghconcat.core.interfaces.net import UrlAcceptPolicyProtocol
from ghconcat.utils.mime import (
    extract_ext_from_url_path,
    infer_extension,
    is_binary_mime,
)
from ghconcat.utils.suffixes import is_suffix_allowed


class DefaultUrlAcceptPolicy(UrlAcceptPolicyProtocol):
    _TEXT_EXT = {
        '.html', '.htm', '.xhtml', '.md', '.markdown', '.txt', '.text',
        '.css', '.scss', '.less', '.js', '.mjs', '.ts', '.tsx', '.jsx',
        '.json', '.jsonc', '.yaml', '.yml', '.xml', '.svg', '.csv', '.tsv',
        '.py', '.rb', '.php', '.pl', '.pm', '.go', '.rs', '.java', '.c',
        '.cpp', '.cc', '.h', '.hpp', '.sh', '.bash', '.zsh', '.ps1', '.r',
        '.lua',
    }
    _BINARY_EXT = {
        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tiff', '.avif',
        '.mp4', '.m4v', '.mov', '.webm', '.ogv', '.flv', '.mp3', '.ogg', '.oga',
        '.wav', '.flac', '.woff', '.woff2', '.ttf', '.otf', '.eot', '.pdf',
        '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.zip', '.tar', '.gz',
        '.tgz', '.bz2', '.xz', '.7z',
    }
    _WELL_KNOWN_EXT = _TEXT_EXT | _BINARY_EXT

    def decide_local_name(self, url: str, idx: int, content_type: str, *, mode: str) -> str:
        name = Path(urlparse(url).path).name or f'remote_{idx}'
        has_dot = '.' in name
        ext = extract_ext_from_url_path(name)

        if mode == 'fetch':
            # In fetch mode, preserve the original basename; only append an
            # inferred extension when the name has no dot at all.
            if not has_dot:
                name += infer_extension(content_type, name, default='.html')
            return name

        # In scrape mode, ensure a sensible extension when the current one is
        # unknown or absent.
        if not ext or ext not in self._WELL_KNOWN_EXT:
            inferred = infer_extension(content_type, name, default='.html')
            if not name.lower().endswith(inferred):
                name += inferred
        return name

    def allowed_by_suffix(self, url: str, *, include: Sequence[str], exclude: Sequence[str]) -> bool:
        ext = extract_ext_from_url_path(urlparse(url).path)
        if not ext:
            return True
        # Reuse the suffix filter used for filesystem paths by creating a dummy filename.
        return is_suffix_allowed(f'f{ext}', set(include), set(exclude))

    def allow_follow(self, abs_url: str, *, base_url: str, same_host_only: bool) -> bool:
        if not same_host_only:
            return True
        b = urlparse(base_url)
        u = urlparse(abs_url)
        return (u.scheme, u.netloc) == (b.scheme, b.netloc)

    def is_binary_type(self, content_type: str) -> bool:
        return is_binary_mime(content_type)