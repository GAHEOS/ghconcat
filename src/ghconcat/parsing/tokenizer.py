from __future__ import annotations

"""
DirectiveTokenizer – canonical tokenizer for directive lines and argv.

This class centralizes:
    * Inline comment stripping while respecting quoted strings.
    * Line tokenization with shlex.
    * Injection of positional paths as '-a PATH' tokens.
      
Backward compatibility: The public free functions in `ghconcat.parsing.tokenize` delegate
 to this class so that external imports and tests remain unchanged.
"""

import shlex
from typing import List, Optional, Set, Tuple
from ghconcat.parsing.attr_sets import _VALUE_FLAGS
from ghconcat.parsing.source import DirectiveSource


class DirectiveTokenizer:
    @staticmethod
    def strip_inline_comments(line: str) -> str:
        """Remove //, # or ; comments out of quotes.

        This preserves literals such as "http://", ignoring '//' when it is
        part of a URL scheme separator (the colon rule).
        """
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
                if ch == '/' and i + 1 < n and (line[i + 1] == '/'):
                    if i == 0 or line[i - 1] != ':':
                        return line[:i]
                elif ch == '#':
                    return line[:i]
                elif ch == ';':
                    return line[:i]
            i += 1
        return line

    @staticmethod
    def tokenize_line(raw: str, *, value_flags: Set[str] = _VALUE_FLAGS) -> List[str]:
        """Tokenize a single directive line into argv-like tokens."""
        stripped = DirectiveTokenizer.strip_inline_comments(raw).strip()
        if not stripped:
            return []
        parts = shlex.split(stripped)
        if not parts:
            return []
        if not parts[0].startswith('-'):
            out: List[str] = []
            for p in parts:
                out.extend(['-a', p])
            return out
        if parts[-1] in value_flags:
            return [*parts, '']
        return parts

    @staticmethod
    def inject_positional_add_paths(tokens: List[str], *, value_flags: Set[str] = _VALUE_FLAGS) -> List[str]:
        """Post-process argv, converting bare positional items into '-a PATH' pairs."""
        out: List[str] = []
        expect_value = False
        for tok in tokens:
            if expect_value:
                out.append(tok)
                expect_value = False
                continue
            if tok.startswith('-'):
                out.append(tok)
                if tok in value_flags:
                    expect_value = True
                continue
            out.extend(['-a', tok])
        return out

    # ---- New: error helper -------------------------------------------------

    @staticmethod
    def safe_tokenize_line(raw: str, src: DirectiveSource, *, value_flags: Set[str] = _VALUE_FLAGS) -> Tuple[
        List[str], Optional[str]]:
        """Tokenize a line and return (tokens, error_message).

        The error_message will be a user-friendly string including the
        source context if shlex raises an exception. We do not raise, to
        keep the current tests behavior invariant.
        """
        try:
            return (DirectiveTokenizer.tokenize_line(raw, value_flags=value_flags), None)
        except Exception as exc:
            # Build a rich, but non-fatal error string the caller may log.
            msg = f"tokenization error at {src.format()}: {exc}"
            return ([], msg)
