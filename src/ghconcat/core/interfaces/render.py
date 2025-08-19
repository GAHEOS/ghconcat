import argparse
from pathlib import Path
from typing import Callable, Dict, List, Protocol


class RendererProtocol(Protocol):
    """Headers/banners/fences composition and template rendering."""

    def concat(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
    ) -> str: ...

    def render_template(self, tpl_path: Path, variables: Dict[str, str], gh_dump: str) -> str: ...

    @property
    def interpolate(self) -> Callable[[str, Dict[str, str]], str]: ...