"""
tokenize – Shared tokenization utilities for ghconcat directive lines.

This module centralizes the directive-line tokenizer to avoid duplication
across the codebase. It reproduces the legacy behavior with two safeguards:

1) Inline comments:
   Strips inline comments introduced by:
     • '//'  – except when part of a URI scheme (e.g., 'https://').
     • '#'   – always, when not inside quotes.
     • ';'   – always, when not inside quotes.
   Quoted strings ('...' or "...") are honored, so comment markers
   inside quotes are not treated as comments.

2) Value-taking flags at line end:
   If the resulting token list ends with a *value-taking* flag (e.g., '-o'),
   an **empty string** is appended to prevent the *next line* from being
   accidentally consumed as the value by argparse.

Additionally, if the first token does not start with '-', each token is
expanded into '-a <token>' (path convenience syntax), matching ghconcat v2.

The function is deliberately kept self-contained and free of side effects
so it can be reused by both the directive parser and any other component
needing identical semantics.
"""
import shlex
from typing import List, Optional

from ghconcat.parsing.flags import VALUE_FLAGS as _VALUE_FLAGS


def _strip_inline_comments(line: str) -> str:
    """Return *line* without inline comments, honoring basic quoting rules.

    Rules
    -----
    • '//' starts a comment unless it is part of a URI scheme token
      such as 'https://', i.e., when the preceding character is ':'.
    • '#' and ';' always start a comment when not inside quotes.
    • Single and double quotes toggle a simple "in-quote" state. Escapes
      are not necessary for the ghconcat directive syntax, and therefore
      are intentionally omitted for simplicity and robustness.
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
       into '-a <token>' (convenience for file/dir paths).
    4) If the final token is a value-taking flag, append an empty string to
       avoid cross-line value consumption during argparse processing.

    Parameters
    ----------
    raw:
        The raw directive line including possible comments.

    Returns
    -------
    List[str]
        The list of tokens or `[]` if the line is blank/comment-only.
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
    """Expand bare tokens into '-a <token>' while respecting value flags.

    This function is the CLI-level counterpart of the per-line tokenizer:
    it processes a **list of pre-tokenized CLI args** (argv tail) and ensures
    positional paths behave as if explicitly passed with `-a`.

    Rules
    -----
    • Any element not starting with '-' is converted to ['-a', token].
    • Flags that expect a value (e.g., '-o FILE') keep their next token
      intact and are not rewritten.
    • The relative/absolute path semantics are handled later by the executor.

    Parameters
    ----------
    tokens:
        CLI-style token list (argv tail).

    Returns
    -------
    List[str]
        A new token list with positional items rewritten.
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