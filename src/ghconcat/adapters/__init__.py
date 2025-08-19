"""
ghconcat.adapters – Adapters that bridge concrete implementations to Protocols.

This package hosts small, dependency-light adapters that wrap concrete classes
and expose stable Protocol-based surfaces. They are *pure delegation layers*
aimed at:
    • Explicit seams for unit tests and mocks.
    • Consistent boundaries for side-effectful code (FS/network).

Modules
-------
git.py     → GitManagerAdapter
url.py     → UrlFetcherAdapter
walker.py  → WalkerAdapter   (new)
"""

from .git import GitManagerAdapter
from .url import UrlFetcherAdapter
from .walker import WalkerAdapter

__all__ = [
    "GitManagerAdapter",
    "UrlFetcherAdapter",
    "WalkerAdapter",
]