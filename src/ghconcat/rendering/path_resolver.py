"""
Path resolver component for ghconcat.

This module provides:
  • PathResolver         – base class with a single-responsibility method.
  • DefaultPathResolver  – explicit default implementation.
  • WorkspaceAwarePathResolver – optional stateful resolver that tracks a
    workspace root and implements a real is_within_workspace(...).

Design goals
------------
• Keep behavior 1:1 with the original implementation by default.
• Stateful resolver remains opt-in and neutral unless a workspace is set.
• The canonical Protocol lives in `ghconcat.core.interfaces.fs`.
"""

from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.fs import PathResolverProtocol  # noqa: F401


class PathResolver:
    """Resolve paths relative to a given base directory.

    Notes
    -----
    • This resolver is intentionally stateless. Optional workspace helpers
      (`workspace_root()` / `is_within_workspace(...)`) return neutral values
      so callers can choose stricter policies without changing defaults.
    """

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Return *maybe* resolved against *base* unless it is absolute."""
        if maybe is None:
            return base
        pth = Path(maybe).expanduser()
        return pth if pth.is_absolute() else (base / pth).resolve()

    def workspace_root(self) -> Path | None:
        """Return the known workspace root if tracked; None for stateless resolver."""
        return None

    def is_within_workspace(self, path: Path) -> bool:
        """Return True when *path* is within the known workspace, else a neutral True.

        Since this default resolver is stateless, it returns True to avoid
        unexpected rejections. Implementations with state should override it.
        """
        root = self.workspace_root()
        if root is None:
            return True
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False


class DefaultPathResolver(PathResolver):
    """Default implementation; kept explicit for dependency injection."""
    pass


class WorkspaceAwarePathResolver(PathResolver):
    """PathResolver with optional workspace tracking and strict checks.

    This resolver is drop-in compatible with the default one, but it allows
    the engine to set the workspace root once it is known. `is_within_workspace`
    performs a real containment check when the root is set, and falls back to
    permissive behavior otherwise.
    """

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        self._workspace: Optional[Path] = workspace

    # ---- state management -------------------------------------------------

    def set_workspace_root(self, root: Optional[Path]) -> None:
        """Update the tracked workspace root (None restores permissive behavior)."""
        self._workspace = root

    # ---- PathResolverProtocol overrides -----------------------------------

    def workspace_root(self) -> Path | None:
        return self._workspace

    def is_within_workspace(self, path: Path) -> bool:
        root = self._workspace
        if root is None:
            return True
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False