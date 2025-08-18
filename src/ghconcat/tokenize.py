"""
tokenize – Shared tokenization utilities for ghconcat directive lines.

This module centralizes the directive-line tokenizer and the CLI positional
path expansion logic (inject_positional_add_paths) to avoid duplication.
"""

from __future__ import annotations

import shlex
from typing import List, Optional

from .flags import VALUE_FLAGS as _VALUE_FLAGS


def _strip_inline_comments(line: str) -> str:
    """Return *line* without inline comments, honoring basic quoting rules.

    Rules
    -----
    • '//' starts a comment unless it is part of a URI scheme token
      such as 'https://', i.e., when the preceding character is ':'.
    • '#' and ';' always start a comment when not inside quotes.
    • Single and double quotes toggle a simple "in-quote" state.
    """
    in_quote: Optional[str] = None
    i, n = 0, len(line)

    while i < n:
        ch = line[i]

        if ch in {"'", '"'}:
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
            i += 1
            continue

        if in_quote is None:
            if ch == "/" and i + 1 < n and line[i + 1] == "/":
                if i == 0 or line[i - 1] != ":":
                    return line[:i]
            elif ch == "#":
                return line[:i]
            elif ch == ";":
                return line[:i]

        i += 1

    return line


def tokenize_directive_line(raw: str) -> List[str]:
    """Split a directive *raw* line into CLI-style tokens.

    Steps (compatible with ghconcat v2)
    -----------------------------------
    1) Strip inline comments (see `_strip_inline_comments`).
    2) Shell-like split with `shlex.split`.
    3) If the first token does **not** start with '-', each token is expanded
       into '-a <token>'.
    4) If the final token is a value-taking flag, append an empty string.
    """
    stripped = _strip_inline_comments(raw).strip()
    if not stripped:
        return []

    parts = shlex.split(stripped)
    if not parts:
        return []

    if not parts[0].startswith("-"):
        out: List[str] = []
        for p in parts:
            out.extend(["-a", p])
        return out

    if parts[-1] in _VALUE_FLAGS:
        return [*parts, ""]

    return parts


def inject_positional_add_paths(tokens: List[str]) -> List[str]:
    """Expand every bare token that does not start with '-' into ['-a', token].

    Rules
    -----
    • Respect value-taking flags by leaving their immediate next token intact.
    • Do not alter tokens that already start with '-'.
    """
    out: List[str] = []
    expect_value = False
    for tok in tokens:
        if expect_value:
            out.append(tok)
            expect_value = False
            continue

        if tok.startswith("-"):
            out.append(tok)
            if tok in _VALUE_FLAGS:
                expect_value = True
            continue

        out.extend(["-a", tok])
    return out