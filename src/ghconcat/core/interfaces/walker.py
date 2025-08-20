"""
core.interfaces.walker – Minimal walker Protocol for ghconcat.

This Protocol abstracts the minimal surface required by high-level components
(Renderer, FileDiscovery), decoupling them from the concrete WalkerAppender
implementation. It enables test doubles and alternative implementations.

The surface mirrors only what collaborators actually use today:
  • gather_files(...)  – discovery of candidate files.
  • concat_files(...)  – concatenation with headers/cleaning/slicing pipeline.
"""

import argparse
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class WalkerProtocol(Protocol):
    """Contract for filesystem walking and concatenation."""

    def gather_files(
            self,
            add_path: List[Path],
            exclude_dirs: List[Path],
            suffixes: List[str],
            exclude_suf: List[str],
    ) -> List[Path]:
        """Enumerate files honoring include/exclude rules and suffix filters."""

    def concat_files(
            self,
            files: List[Path],
            ns: argparse.Namespace,
            *,
            header_root: Path,
            wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """Concatenate files according to CLI-like flags in *ns*."""
