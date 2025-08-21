from __future__ import annotations
"""HTML file reader that converts markup to plain text.

This reader attempts lxml, falls back to ElementTree, and finally uses a
regex-based stripper as a last resort. It returns lines including their
trailing newline characters in order to match other reader behaviors.
"""
import logging
import re
from pathlib import Path
from typing import Optional

from ghconcat.io.readers import FileReader
from ghconcat.logging.helpers import get_logger

_TAG_RE = re.compile('<[^>]+>')


class HtmlToTextReader(FileReader):
    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or get_logger('io.readers.html')

    def read_lines(self, path: Path) -> list[str]:
        try:
            raw = path.read_text(encoding='utf-8', errors='ignore')
        except UnicodeDecodeError:
            self._log.warning('✘ %s: binary or non-UTF-8 file skipped.', path)
            return []
        except Exception as exc:
            self._log.error('⚠  could not read %s (%s)', path, exc)
            return []

        text = self._html_to_text(raw)
        if not text:
            return []
        return [ln + '\n' for ln in text.splitlines()]

    @staticmethod
    def _html_to_text(src: str) -> str:
        try:
            from lxml import etree as _ET

            parser = _ET.HTMLParser(recover=True)
            root = _ET.fromstring(src, parser=parser)
            return '\n'.join((t for t in root.itertext() if t.strip()))
        except Exception:
            pass

        try:
            import xml.etree.ElementTree as _ET

            root = _ET.fromstring(src)
            return '\n'.join((t for t in root.itertext() if t.strip()))
        except Exception:
            return re.sub('[ \t]+\n', '\n', _TAG_RE.sub(' ', src)).strip()