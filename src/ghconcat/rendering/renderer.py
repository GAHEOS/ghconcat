"""
Renderer component for ghconcat.

This module provides:
  • RendererProtocol – DI-friendly interface (from core.interfaces.render).
  • Renderer         – concatenation + optional wrapping + templating.

Notes
-----
• Concatenation is delegated to a Walker (Protocol-based) instead of the
  concrete WalkerAppender, which improves testability and decoupling.
• Wrapping produces fenced code blocks while honoring banner headers and
  the global HEADER_DELIM string injected via constructor.
• NEW: The renderer now depends on a TemplateEngineProtocol implementation
  (SingleBraceTemplateEngine by default in the runtime container).
"""

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol


class Renderer(RendererProtocol):
    """Concatenate files and optionally apply wrapping & templating."""

    def __init__(
        self,
        *,
        walker: WalkerProtocol,
        template_engine: TemplateEngineProtocol,
        header_delim: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._walker = walker
        self._tpl_engine = template_engine
        self._hdr = header_delim
        self._log = logger or logging.getLogger("ghconcat.render")

    def concat(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
    ) -> str:
        """Concatenate *files* according to *ns* (Walker-based)."""
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

    def render_template(self, tpl_path: Path, variables: Dict[str, str], gh_dump: str) -> str:  # type: ignore[override]
        """Render the template file applying the configured template engine."""
        tpl = tpl_path.read_text(encoding="utf-8")
        return self._tpl_engine.render(tpl, {**variables, "ghconcat_dump": gh_dump})

    @property
    def interpolate(self) -> Callable[[str, Dict[str, str]], str]:  # type: ignore[override]
        """Return a callable compatible with the legacy interpolate signature.

        This preserves compatibility for callers that expect a function-like
        interpolation surface from the renderer (e.g., system prompt files).
        """
        return lambda tpl, mapping: self._tpl_engine.render(tpl, mapping)