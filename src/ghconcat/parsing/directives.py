"""
directives – Directive file parsing utilities for ghconcat.

This module extracts the directive-file parsing logic from the monolithic
implementation into a dedicated, reusable unit. It provides:

- DirNode: a minimal tree structure holding tokens per context.
- DirectiveParser: OO parser with parse()/parse_lines()/validate().
- parse_directive_file(...): a thin wrapper for backwards compatibility.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from ghconcat.parsing.attr_sets import _VALUE_FLAGS
from ghconcat.parsing.tokenize import tokenize_directive_line


class DirectiveSyntaxError(ValueError):
    """Raised on malformed directive file syntax (with line/column hints)."""


@dataclass
class DirNode:
    """Minimal tree node representing a directive `[context]` block.

    Attributes
    ----------
    name:
        Optional context name. The root node has `name=None`.
    tokens:
        Flat list of CLI-like tokens accumulated for this node.
    children:
        Nested child contexts in file order.
    """
    name: Optional[str] = None
    tokens: List[str] = field(default_factory=list)
    children: List["DirNode"] = field(default_factory=list)


_HEADER_RE = re.compile(r"^\s*\[(?P<name>[^\]]*)]\s*$")


class DirectiveParser:
    """OO parser for ghconcat directive files with strict validation.

    The parsing semantics match ghconcat v2 with two safeguards that avoid
    cross-line token bleeding and honor inline comments, as implemented by
    the shared tokenizer.

    Parameters
    ----------
    logger:
        Optional logger instance for consistent logs; parsing errors raise
        `DirectiveSyntaxError` with precise line numbers.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.dirparser")

    def parse(self, path: Path) -> DirNode:
        """Parse *path* into a DirNode tree with clear syntax validation."""
        with path.open("r", encoding="utf-8") as fp:
            return self.parse_lines(fp.readlines())

    def parse_lines(self, lines: Iterable[str]) -> DirNode:
        """Parse an iterable of lines into a DirNode tree."""
        root = DirNode()
        current = root

        def _finalize(node: DirNode) -> None:
            """Validate a node's token list, appending empty value if needed."""
            node.tokens = self.validate(node.tokens)

        for lno, raw in enumerate(lines, start=1):
            s = raw.strip()

            if s.startswith("[") and "]" not in s:
                raise DirectiveSyntaxError(
                    f"unterminated context header at line {lno}: missing ']'"
                )

            m = _HEADER_RE.match(s)
            if m:
                # Close the previous node before starting a new context.
                _finalize(current)

                name = (m.group("name") or "").strip()
                if not name:
                    raise DirectiveSyntaxError(f"empty context name at line {lno}")
                node = DirNode(name=name)
                root.children.append(node)
                current = node
                continue

            toks = tokenize_directive_line(raw)
            if toks:
                current.tokens.extend(toks)

        # Finalize the last active node (root or last child).
        _finalize(current)
        return root

    def validate(self, tokens: List[str]) -> List[str]:
        """Ensure a trailing value-taking flag gets an empty value."""
        if tokens and tokens[-1] in _VALUE_FLAGS:
            return [*tokens, ""]
        return tokens


def parse_directive_file(path: Path) -> DirNode:
    """Backwards-compatible functional parser wrapper."""
    return DirectiveParser().parse(path)