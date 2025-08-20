"""
Utilities for suffix normalization and allow/deny checks across the codebase.

The goal is to remove logic duplication when handling:
  • Inclusion suffixes (-s/--suffix)
  • Exclusion suffixes (-S/--exclude-suffix)
  • Precedence: include > exclude
"""

from typing import Iterable, Sequence, Set, Tuple


def normalize_suffixes(suffixes: Sequence[str] | None) -> list[str]:
    """Return a normalized list ensuring every suffix starts with a dot.

    Examples:
        ['py', '.js'] -> ['.py', '.js']
    """
    if not suffixes:
        return []
    return [(s if s.startswith(".") else f".{s}") for s in suffixes]


def compute_suffix_filters(
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
) -> Tuple[Set[str], Set[str]]:
    """Compute include/exclude sets with include precedence.

    Rules
    -----
    • Include list is normalized and used as-is.
    • Exclude list is normalized and any overlap with include is removed
      so that include > exclude.
    """
    inc = set(normalize_suffixes(include))
    exc = set(normalize_suffixes(exclude)) - inc
    return inc, exc


def is_suffix_allowed(filename: str, include: Set[str], exclude: Set[str]) -> bool:
    """Return True if *filename* is allowed by suffix filters.

    Semantics (compatible with ghconcat):
      • When include is non-empty → the filename must match ANY include suffix.
      • Exclude is always applied (after include precedence was already handled).
    """
    if include and not any(filename.endswith(s) for s in include):
        return False
    if any(filename.endswith(s) for s in exclude):
        return False
    return True