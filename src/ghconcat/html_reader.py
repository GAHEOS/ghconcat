"""
html_reader – Pluggable HTML → plaintext reader for ghconcat.

This module provides an HtmlToTextReader that converts HTML documents to
plain text. It is designed to be plugged into the global ReaderRegistry
(e.g., when the CLI flag `-K/--textify-html` is active).

No dependency on the monolithic module is introduced to avoid circular
imports. HTML parsing is performed with lxml when available, otherwise
falls back to xml.etree.ElementTree and finally to a regex-based stripper.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from .readers import FileReader


_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(src: str) -> str:
    """Return a plain-text representation of *src* (HTML document/fragment).

    Resolution order:
      1) lxml.etree: fromstring(..., HTMLParser(recover=True)) + itertext()
      2) xml.etree.ElementTree: fromstring(...) + itertext()
      3) Fallback: strip all tags with regex and collapse whitespace.

    Parameters
    ----------
    src:
        Raw HTML document or fragment.

    Returns
    -------
    str
        Extracted plain text with basic whitespace normalization.
    """
    try:
        from lxml import etree as _ET  # type: ignore
        parser = _ET.HTMLParser(recover=True)
        root = _ET.fromstring(src, parser=parser)
        return "\n".join(t for t in root.itertext() if t.strip())
    except Exception:  # noqa: BLE001
        pass

    try:
        import xml.etree.ElementTree as _ET  # type: ignore
        root = _ET.fromstring(src)
        return "\n".join(t for t in root.itertext() if t.strip())
    except Exception:  # noqa: BLE001
        # Final fallback → remove tags and normalize trailing spaces before \n
        return re.sub(r"[ \t]+\n", "\n", _TAG_RE.sub(" ", src)).strip()


class HtmlToTextReader(FileReader):
    """HTML → plaintext reader.

    The reader loads the file as UTF-8 (with `errors="ignore"`) and then
    applies an HTML-to-text conversion routine. It never raises for binary
    or undecodable files; it returns an empty list in such cases.

    Parameters
    ----------
    logger:
        Optional logger instance for consistent logs across the library.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers.html")

    def read_lines(self, path: Path) -> list[str]:
        """Return the HTML contents as **plain-text lines** ending with '\\n'.

        Parameters
        ----------
        path:
            File system path to an .html file.

        Returns
        -------
        List[str]
            The converted text split into lines with trailing '\\n'.
        """
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except UnicodeDecodeError:
            self._log.warning("✘ %s: binary or non-UTF-8 file skipped.", path)
            return []
        except Exception as exc:  # noqa: BLE001
            self._log.error("⚠  could not read %s (%s)", path, exc)
            return []

        text = _html_to_text(raw)
        if not text:
            return []
        return [ln + "\n" for ln in text.splitlines()]