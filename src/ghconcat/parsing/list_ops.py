"""
listops – Small, shared list operations for ghconcat.

This module centralizes tiny, widely useful list utilities to avoid
duplication across components (e.g., ExecutionEngine). Kept intentionally
minimal and dependency-free.
"""
import re
from typing import List, Optional


def split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma- and space-separated tokens.

    Examples
    --------
    >>> split_list([".py,.js", ".ts  .tsx"])
    ['.py', '.js', '.ts', '.tsx']

    Parameters
    ----------
    raw:
        Optional list of strings, each possibly containing comma- and/or
        whitespace-separated items.

    Returns
    -------
    List[str]
        A new list with individual tokens, empty items removed.
    """
    if not raw:
        return []
    out: List[str] = []
    for itm in raw:
        out.extend([x for x in re.split(r"[,\s]+", itm) if x])
    return out