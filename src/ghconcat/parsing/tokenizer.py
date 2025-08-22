from __future__ import annotations

"""
DirectiveTokenizer – canonical tokenizer for directive lines and argv.

This class centralizes:
    * Inline comment stripping while respecting quoted strings.
    * Line tokenization with shlex.
    * Injection of positional paths as '-a PATH' tokens.

Refactor:
    - Unified positional injection logic into a single helper
      `_inject_positional(...)`, used by both `tokenize_line` and
      `inject_positional_add_paths` to remove duplication while preserving
      behavior (including trailing value-flag placeholder handling).
"""

import shlex
from typing import List, Optional, Set, Tuple

from ghconcat.parsing.attr_sets import _VALUE_FLAGS
from ghconcat.parsing.source import DirectiveSource


class DirectiveTokenizer:
    @staticmethod
    def strip_inline_comments(line: str) -> str:
        in_quote: Optional[str] = None
        i, n = (0, len(line))
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
                if ch == "/" and i + 1 < n and (line[i + 1] == "/"):
                    if i == 0 or line[i - 1] != ":":
                        return line[:i]
                elif ch == "#":
                    return line[:i]
                elif ch == ";":
                    return line[:i]
            i += 1
        return line

    @staticmethod
    def _inject_positional(tokens: List[str], *, value_flags: Set[str]) -> List[str]:
        """Inject '-a' before bare positional tokens outside value positions.

        The algorithm:
            - Walk tokens left-to-right keeping track of "expecting a value"
              (last token was a value flag).
            - If a token starts with '-' or we are fulfilling a value flag,
              keep it as-is.
            - Otherwise, expand it as ['-a', token].
            - If the *last* token is a value flag, append an empty string
              (compatibility with previous behavior).

        Args:
            tokens: Raw tokens (already split, comments removed).
            value_flags: Set of flags that expect a value.

        Returns:
            A new list of tokens with '-a' injections applied.
        """
        if not tokens:
            return []

        out: List[str] = []
        expect_value = False
        for tok in tokens:
            if expect_value:
                out.append(tok)
                expect_value = False
                continue
            if tok.startswith("-"):
                out.append(tok)
                if tok in value_flags:
                    expect_value = True
                continue
            # bare positional → inject as '-a', value
            out.extend(["-a", tok])

        # If the last token was a value flag, append an empty placeholder
        if tokens[-1] in value_flags:
            out.append("")

        return out

    @staticmethod
    def tokenize_line(raw: str, *, value_flags: Set[str] = _VALUE_FLAGS) -> List[str]:
        stripped = DirectiveTokenizer.strip_inline_comments(raw).strip()
        if not stripped:
            return []
        parts = shlex.split(stripped)
        if not parts:
            return []
        # Unified path: inject positionals while honoring value flags.
        return DirectiveTokenizer._inject_positional(parts, value_flags=value_flags)

    @staticmethod
    def inject_positional_add_paths(
        tokens: List[str], *, value_flags: Set[str] = _VALUE_FLAGS
    ) -> List[str]:
        """Inject '-a PATH' for CLI positional tokens in a token stream."""
        return DirectiveTokenizer._inject_positional(tokens, value_flags=value_flags)

    @staticmethod
    def safe_tokenize_line(
        raw: str, src: DirectiveSource, *, value_flags: Set[str] = _VALUE_FLAGS
    ) -> Tuple[List[str], Optional[str]]:
        try:
            return (DirectiveTokenizer.tokenize_line(raw, value_flags=value_flags), None)
        except Exception as exc:
            msg = f"tokenization error at {src.format()}: {exc}"
            return ([], msg)