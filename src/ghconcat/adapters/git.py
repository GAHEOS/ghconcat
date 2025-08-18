"""
adapters.git – Adapter to expose a concrete Git manager via the Protocol.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..core import GitRepositoryManagerProtocol
from ghconcat.discovery.git_repository import GitRepositoryManager


@dataclass
class GitManagerAdapter(GitRepositoryManagerProtocol):
    """Adapter that fulfills GitRepositoryManagerProtocol by delegation.

    The adapter wraps :class:`GitRepositoryManager` (concrete implementation)
    and forwards calls 1:1, keeping a clean, test-friendly Protocol surface.

    Notes
    -----
    • This adapter is intentionally thin. Any behavioral logic belongs in the
      concrete manager. The adapter exists to decouple imports at boundaries.
    """

    target: GitRepositoryManager

    def collect_files(  # type: ignore[override]
        self,
        git_specs: List[str],
        git_exclude: List[str],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Delegate to the wrapped GitRepositoryManager."""
        return self.target.collect_files(git_specs, git_exclude, suffixes, exclude_suf)