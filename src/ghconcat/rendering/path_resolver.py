from __future__ import annotations
"""
Path resolver utilities.

This module consolidates the default path resolver to the workspace-aware
implementation while preserving public API compatibility:

- `DefaultPathResolver` is now an alias of `WorkspaceAwarePathResolver`.
- Base `PathResolver` also tracks a workspace root so that all concrete
  resolvers behave consistently.
- `PathResolverProtocol` is re-exported here to preserve the import path
  used in ghconcat.__init__.

Design goals:
- Keep the API stable for external imports.
- Enforce workspace-aware safety where requested by the engine.
"""

from pathlib import Path
from typing import Optional

# Re-export the protocol to preserve import compatibility:
from ghconcat.core.interfaces.fs import PathResolverProtocol as _PathResolverProtocol
PathResolverProtocol = _PathResolverProtocol


class PathResolver(PathResolverProtocol):
    """Basic path resolver with optional workspace awareness.

    This base implementation keeps a workspace root reference and offers
    helpers used by the engine to guard paths.
    """

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        self._workspace: Optional[Path] = workspace

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Resolve `maybe` against `base`, expanding '~' if present."""
        if maybe is None:
            return base
        pth = Path(maybe).expanduser()
        return pth if pth.is_absolute() else (base / pth).resolve()

    # Workspace handling -----------------------------------------------------

    def workspace_root(self) -> Optional[Path]:
        """Return the current workspace root (if any)."""
        return self._workspace

    def set_workspace_root(self, root: Optional[Path]) -> None:
        """Set/clear the workspace root for subsequent path guards."""
        self._workspace = root

    def is_within_workspace(self, path: Path) -> bool:
        """Return True if `path` is inside the current workspace (or no workspace set)."""
        root = self.workspace_root()
        if root is None:
            return True
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False


class WorkspaceAwarePathResolver(PathResolver):
    """Concrete resolver that always considers a workspace (when provided).

    This class exists for semantic clarity. It inherits the workspace logic
    from `PathResolver` and adds no extra behavior.
    """

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        super().__init__(workspace=workspace)


# Public default – consolidated to the workspace-aware implementation.
DefaultPathResolver = WorkspaceAwarePathResolver