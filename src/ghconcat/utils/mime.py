from __future__ import annotations
import mimetypes
import re
from typing import Mapping, Optional

_EXT_RE = re.compile(r'\.[A-Za-z0-9_-]{1,8}$')

# Centralized default fallback for common textual MIME types.
DEFAULT_MIME_EXT_FALLBACK: Mapping[str, str] = {
    'text/html': '.html',
    'application/json': '.json',
    'application/javascript': '.js',
    'text/css': '.css',
    'text/plain': '.txt',
    'text/xml': '.xml',
}


def extract_ext_from_url_path(url_path: str) -> str:
    m = _EXT_RE.search(url_path or '')
    return m.group(0).lower() if m else ''


def is_binary_mime(ctype: str) -> bool:
    if not ctype:
        return False
    if ctype.startswith('text/') or ctype.endswith(('+xml', '+json', '+html')):
        return False
    if ctype in ('application/json', 'application/javascript', 'application/xml'):
        return False
    return True


def infer_extension(
    ctype: str,
    url_path: str,
    default: str = '.html',
    *,
    fallback: Optional[Mapping[str, str]] = None,
) -> str:
    """Infer a file extension from a Content-Type or URL path.

    Args:
        ctype: Content-Type header value.
        url_path: URL path (used as a hint).
        default: Extension to use if nothing else matches.
        fallback: Optional override mapping for specific MIME types.

    Returns:
        The chosen extension, including the leading dot.
    """
    fb = fallback or DEFAULT_MIME_EXT_FALLBACK
    if ctype in fb:
        return fb[ctype]

    guessed = mimetypes.guess_extension(ctype or '')
    if guessed:
        return guessed

    ext = extract_ext_from_url_path(url_path)
    if ext:
        return ext

    return default