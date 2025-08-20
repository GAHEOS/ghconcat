from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Protocol, runtime_checkable


@runtime_checkable
class RendererProtocol(Protocol):
    """Renders concatenated text and simple brace-based templates."""

    def concat(self, files: list[Path], ns: argparse.Namespace, *, header_root: Path) -> str:
        """Concatenate file contents honoring slicing/cleaning options in `ns`."""
        ...

    def render_template(self, template_path: Path, vars_local: Dict[str, str], dump: str) -> str:
        """Render a file-based template with variables and a global dump payload."""
        ...

    def interpolate(self, template_text: str, vars_local: Dict[str, str]) -> str:
        """Render an in-memory template string with variables (no file I/O)."""
        ...