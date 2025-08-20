from __future__ import annotations

import mimetypes
import re
from typing import Mapping, Optional

_EXT_RE = re.compile(r"\.[A-Za-z0-9_-]{1,8}$")


def extract_ext_from_url_path(url_path: str) -> str:
    """Extract a normalized extension from a URL path or filename.

    Args:
        url_path: Final path segment or full path of the URL.

    Returns:
        Lower-cased extension including the dot (e.g., '.html'), or empty string.
    """
    m = _EXT_RE.search(url_path or "")
    return m.group(0).lower() if m else ""


def is_binary_mime(ctype: str) -> bool:
    """Return True if the mime type is typically binary for our use-case.

    Textual types and common +xml/+json/+html structured types are considered text.
    """
    if not ctype:
        return False
    if ctype.startswith("text/") or ctype.endswith(("+xml", "+json", "+html")):
        return False
    if ctype in ("application/json", "application/javascript", "application/xml"):
        return False
    return True


def infer_extension(
    ctype: str,
    url_path: str,
    default: str = ".html",
    *,
    fallback: Optional[Mapping[str, str]] = None,
) -> str:
    """Infer a filename extension based on content type and URL path.

    Resolution order:
      1) fallback mapping (if provided)
      2) mimetypes.guess_extension
      3) extension present in the URL path
      4) supplied default

    Args:
        ctype: Content-Type without parameters (e.g., 'text/html').
        url_path: Path or filename to inspect for an extension fallback.
        default: Default extension to use as a last resort.
        fallback: Optional mapping of mime -> extension overrides.

    Returns:
        A dot-prefixed extension string.
    """
    if fallback and ctype in fallback:
        return fallback[ctype]  # type: ignore[return-value]

    guessed = mimetypes.guess_extension(ctype or "")
    if guessed:
        return guessed

    ext = extract_ext_from_url_path(url_path)
    if ext:
        return ext

    return default