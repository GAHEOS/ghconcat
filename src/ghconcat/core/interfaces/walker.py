import argparse
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class WalkerProtocol(Protocol):
    """Abstraction for file discovery + concatenation with cleaning."""

    def gather_files(self, add_path: List[Path], exclude_dirs: List[Path], suffixes: List[str], exclude_suf: List[str]) -> List[Path]: ...
    def concat_files(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str: ...