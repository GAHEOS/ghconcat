from __future__ import annotations
"""Suffix utilities for include/exclude filters.

This module centralizes how CLI tokens passed via `-s/--suffix` and
`-S/--exclude-suffix` are normalized and applied.

Semantics (backward compatible, extended for filename tails):
    * Tokens WITHOUT a dot are treated as bare extensions and normalized by
      prefixing a dot. Example: "py" -> ".py".
    * Tokens WITH a dot anywhere are treated as explicit "filename tail"
      patterns and left AS-IS. Examples:
        - ".py" stays ".py"  (classic extension-based suffix)
        - "__init__.py" stays "__init__.py"  (basename tail)
        - "my.config" stays "my.config"  (multi-part tail)
    * Matching is performed with `str.endswith(...)` over the filename
      (not the full path), so tails like "__init__.py" work as expected.

Examples:
    normalize_suffixes(["py"])            -> [".py"]
    normalize_suffixes([".py"])           -> [".py"]
    normalize_suffixes(["__init__.py"])   -> ["__init__.py"]
    normalize_suffixes(["my.config"])     -> ["my.config"]

This allows flags like:
    -S __init__.py     # exclude only files named __init__.py
    -S .testext        # exclude files by extension .testext
    -s .py             # include .py files
    -s __init__.py     # include only files ending with "__init__.py"

The matcher below (`is_suffix_allowed`) keeps the original policy:
    - If `include` is non-empty, a filename must match AT LEAST one include.
    - Then any match against `exclude` rejects the file.
"""

from typing import Sequence, Set, Tuple


def normalize_suffixes(suffixes: Sequence[str] | None) -> list[str]:
    """Normalize suffix tokens from CLI.

    Args:
        suffixes: Raw tokens from `-s/--suffix` or `-S/--exclude-suffix`.

    Returns:
        A normalized list of tokens suitable for `str.endswith(...)` matches.
    """
    if not suffixes:
        return []
    out: list[str] = []
    for raw in suffixes:
        s = (raw or "").strip()
        if not s:
            continue
        # If token has NO dot, treat as bare extension and prefix a dot.
        # If token HAS a dot anywhere, treat it as an explicit filename-tail and keep as-is.
        if "." in s:
            out.append(s)
        else:
            out.append(f".{s}")
    return out


def compute_suffix_filters(include: Sequence[str] | None, exclude: Sequence[str] | None) -> Tuple[Set[str], Set[str]]:
    """Compute include/exclude sets with proper normalization and deduplication."""
    inc = set(normalize_suffixes(include))
    exc = set(normalize_suffixes(exclude)) - inc
    return (inc, exc)


def is_suffix_allowed(filename: str, include: Set[str], exclude: Set[str]) -> bool:
    """Return True if a filename passes include/exclude suffix filters.

    Args:
        filename: Basename of the file to test (not a full path).
        include: Set of allowed suffix/tails (empty = allow all).
        exclude: Set of rejected suffix/tails.

    Policy:
        - If `include` is non-empty, filename must end with any item in `include`.
        - If `exclude` contains any item that matches `filename.endswith(...)`, reject.
    """
    if include and (not any((filename.endswith(s) for s in include))):
        return False
    if any((filename.endswith(s) for s in exclude)):
        return False
    return True