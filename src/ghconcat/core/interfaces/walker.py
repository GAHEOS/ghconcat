from __future__ import annotations
import argparse
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class WalkerProtocol(Protocol):
    """Abstract file walker/concatenator."""

    def gather_files(
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Collect candidate files honoring include/exclude suffix rules."""
        ...

    def concat_files(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """Concatenate file contents into a single string."""
        ...