from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.fs import PathResolverProtocol


class PathResolver(PathResolverProtocol):
    """Resolve and validate filesystem paths with optional workspace awareness."""

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Resolve `maybe` against `base` (supports absolute and `~`)."""
        if maybe is None:
            return base
        pth = Path(maybe).expanduser()
        return pth if pth.is_absolute() else (base / pth).resolve()

    def workspace_root(self) -> Path | None:
        """Return the active workspace root, if any."""
        return None

    def is_within_workspace(self, path: Path) -> bool:
        """Check whether `path` is inside the current workspace root (if set)."""
        root = self.workspace_root()
        if root is None:
            return True
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False


class DefaultPathResolver(PathResolver):
    """Default resolver with no workspace restrictions."""
    pass


class WorkspaceAwarePathResolver(PathResolver):
    """Resolver that can enforce a workspace root boundary."""

    def __init__(self, *, workspace: Optional[Path] = None) -> None:
        self._workspace: Optional[Path] = workspace

    def set_workspace_root(self, root: Optional[Path]) -> None:
        """Dynamically update the workspace root."""
        self._workspace = root

    def workspace_root(self) -> Path | None:
        return self._workspace

    def is_within_workspace(self, path: Path) -> bool:
        """Delegate to base implementation to avoid duplication."""
        return super().is_within_workspace(path)
