import logging
import re
from pathlib import Path
from typing import Optional

from ghconcat.io.readers import FileReader

_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(src: str) -> str:
    """Backward-compatible wrapper around HtmlToTextReader._html_to_text()."""
    return HtmlToTextReader._html_to_text(src)


class HtmlToTextReader(FileReader):
    """Reads HTML files and returns plain text lines.

    This reader attempts a robust HTML-to-text conversion:
    1) Try lxml's HTML parser (best effort, tolerant).
    2) Fallback to Python's built-in ElementTree for XML-like HTML.
    3) As a last resort, strip tags via regex and normalize whitespace.

    The contract matches FileReader: returns a list of lines with trailing
    newlines preserved.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers.html")

    def read_lines(self, path: Path) -> list[str]:
        """Read an HTML file and convert it to plain text lines.

        Args:
            path: Path to the HTML file.

        Returns:
            A list of lines (each ending with '\n'). Empty if unreadable or
            conversion produced no text.
        """
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except UnicodeDecodeError:
            self._log.warning("✘ %s: binary or non-UTF-8 file skipped.", path)
            return []
        except Exception as exc:
            self._log.error("⚠  could not read %s (%s)", path, exc)
            return []

        text = self._html_to_text(raw)
        if not text:
            return []
        return [ln + "\n" for ln in text.splitlines()]

    # ---- Internals ---------------------------------------------------------

    @staticmethod
    def _html_to_text(src: str) -> str:
        """Convert an HTML string into a best-effort plain text.

        Strategy:
          * Use lxml if available (most resilient).
          * Fallback to ElementTree (XML-like).
          * Finally, strip tags with a regex and collapse excess spaces.

        Args:
            src: Raw HTML string.

        Returns:
            Plain text string with newlines preserved.
        """
        # Best-effort, tolerant HTML parsing
        try:
            from lxml import etree as _ET  # type: ignore

            parser = _ET.HTMLParser(recover=True)
            root = _ET.fromstring(src, parser=parser)
            return "\n".join((t for t in root.itertext() if t.strip()))
        except Exception:
            pass

        # XML-ish fallback
        try:
            import xml.etree.ElementTree as _ET

            root = _ET.fromstring(src)
            return "\n".join((t for t in root.itertext() if t.strip()))
        except Exception:
            # Last resort: strip tags and normalize whitespace
            return re.sub(r"[ \t]+\n", "\n", _TAG_RE.sub(" ", src)).strip()