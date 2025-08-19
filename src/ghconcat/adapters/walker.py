"""
adapters.walker – Adapter to expose a concrete Walker via the Protocol.

This adapter wraps the concrete :class:`WalkerAppender` and exposes the
minimal :class:`WalkerProtocol` surface. It is intentionally thin and kept
as a pure delegation layer to allow swapping the underlying implementation
(e.g., a memory-index walker) without touching collaborators.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import argparse

from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.io.walker import WalkerAppender


@dataclass
class WalkerAdapter(WalkerProtocol):
    """Adapter that fulfills WalkerProtocol by delegation."""

    target: WalkerAppender

    def gather_files(  # type: ignore[override]
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Delegate discovery to the wrapped Walker."""
        return self.target.gather_files(add_path, exclude_dirs, suffixes, exclude_suf)

    def concat_files(  # type: ignore[override]
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """Delegate concatenation to the wrapped Walker."""
        return self.target.concat_files(files, ns, header_root=header_root, wrapped=wrapped)