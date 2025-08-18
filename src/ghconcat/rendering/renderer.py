"""
Renderer component for ghconcat.

This module provides:
  • RendererProtocol – DI-friendly interface.
  • Renderer         – concatenation + optional wrapping + templating.

Notes
-----
• Concatenation is delegated to WalkerAppender (same as legacy behavior).
• Wrapping produces fenced code blocks while honoring banner headers and
  the global HEADER_DELIM string injected via constructor.
"""

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from ghconcat.io.walker import WalkerAppender


@runtime_checkable
class RendererProtocol(Protocol):
    """Protocol describing the renderer component."""

    def concat(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
    ) -> str:
        """Concatenate *files* into a single string according to *ns* flags."""

    def render_template(self, tpl_path: Path, variables: Dict[str, str], gh_dump: str) -> str:
        """Render a template applying single-brace interpolation."""

    @property
    def interpolate(self) -> Callable[[str, Dict[str, str]], str]:
        """Return the interpolation function used by this renderer."""


class Renderer(RendererProtocol):
    """Concatenate files and optionally apply wrapping & templating."""

    def __init__(
        self,
        *,
        walker: WalkerAppender,
        interpolate: Callable[[str, Dict[str, str]], str],
        header_delim: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._walker = walker
        self._interpolate = interpolate
        self._hdr = header_delim
        self._log = logger or logging.getLogger("ghconcat.render")

    def concat(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
    ) -> str:
        """Concatenate *files* according to *ns* (WalkerAppender-based)."""
        wrapped: Optional[List[Tuple[str, str]]] = [] if ns.wrap_lang else None
        dump_raw = self._walker.concat_files(
            files, ns, header_root=header_root, wrapped=wrapped
        )

        if ns.wrap_lang and wrapped:
            fenced: List[str] = []
            for hp, body in wrapped:
                hdr = "" if ns.skip_headers else f"{self._hdr}{hp} {self._hdr}\n"
                fenced.append(
                    f"{hdr}```{ns.wrap_lang or Path(hp).suffix.lstrip('.')}\n"
                    f"{body}\n```\n"
                )
            dump_raw = "".join(fenced)

        return dump_raw

    def render_template(self, tpl_path: Path, variables: Dict[str, str], gh_dump: str) -> str:
        """Render the template file applying {single-brace} interpolation."""
        tpl = tpl_path.read_text(encoding="utf-8")
        return self._interpolate(tpl, {**variables, "ghconcat_dump": gh_dump})

    @property
    def interpolate(self) -> Callable[[str, Dict[str, str]], str]:
        """Return the interpolation function used by this renderer."""
        return self._interpolate