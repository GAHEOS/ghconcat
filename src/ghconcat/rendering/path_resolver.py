"""
Path resolver component for ghconcat.

This module provides:
  • PathResolverProtocol – a minimal typing protocol for DI.
  • PathResolver         – base class with a single-responsibility method.
  • DefaultPathResolver  – explicit default implementation.

Design goals
------------
• Keep behavior 1:1 with the original in-module class.
• Allow independent unit testing and DI in the execution engine.
"""

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PathResolverProtocol(Protocol):
    """Protocol describing a path resolver component."""

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Return *maybe* resolved against *base* unless absolute."""


class PathResolver:
    """Resolve paths relative to a given base directory."""

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Return *maybe* resolved against *base* unless it is absolute."""
        if maybe is None:
            return base
        pth = Path(maybe).expanduser()
        return pth if pth.is_absolute() else (base / pth).resolve()


class DefaultPathResolver(PathResolver):
    """Default implementation; kept explicit for dependency injection."""
    pass