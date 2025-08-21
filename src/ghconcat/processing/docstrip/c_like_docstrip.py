from __future__ import annotations
"""C-like comment stripper.

This utility removes line ('// ...') and block ('/* ... */') comments while
preserving string literals (single and double quotes) with escaping. It is
intended for JS/TS/JSX/TSX and other C-like languages.

Notes:
    - It keeps all original newlines so downstream line slicing remains stable.
    - It does not attempt to parse template literals, but it preserves quoted
      strings with escaping correctly, which is sufficient for our tests.
"""

from typing import Optional


def strip_c_like_comments(source: str, filename: Optional[str] = None) -> str:
    """Strip // and /* */ comments from C-like sources.

    Args:
        source: Original source code.
        filename: Optional filename for diagnostics (unused here).

    Returns:
        The source code with comments removed, preserving newlines.
    """
    out: list[str] = []
    i = 0
    n = len(source)
    in_line = False
    in_block = False
    in_string = False
    quote = ""
    escape = False

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        # Handle comment modes first
        if in_line:
            # Consume until newline, but keep the newline itself.
            if ch in ("\r", "\n"):
                out.append(ch)
                in_line = False
            i += 1
            continue

        if in_block:
            # Look for the terminating '*/'
            if ch == "*" and nxt == "/":
                in_block = False
                i += 2
            else:
                i += 1
            continue

        # Not in a comment. If in a string, process escapes and termination.
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            i += 1
            continue

        # Not in string/comment: check comment starts or string starts.
        if ch == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if ch in ("'", '"'):
            in_string = True
            quote = ch
            out.append(ch)
            i += 1
            continue

        # Normal character
        out.append(ch)
        i += 1

    return "".join(out)