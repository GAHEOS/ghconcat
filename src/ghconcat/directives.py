"""
directives – Directive file parsing utilities for ghconcat.

OO parser (`DirectiveParser`) with explicit validation split from tokenization.
Maintains full backwards compatibility with existing functions/behavior.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import logging
import re

from .flags import VALUE_FLAGS as _VALUE_FLAGS
from .tokenize import tokenize_directive_line


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
    """Object-oriented directive parser with explicit validation hooks.

    Parameters
    ----------
    logger:
        Optional logger used to report non-fatal information. Fatal syntax
        validation still raises `DirectiveSyntaxError`.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.directives")

    def parse(self, path: Path) -> DirNode:
        """Parse a directive file *path* into a `DirNode` tree."""
        lines = path.read_text(encoding="utf-8").splitlines(True)
        return self.parse_lines(lines)

    def parse_lines(self, lines: List[str]) -> DirNode:
        """Parse preloaded *lines* into a `DirNode` tree."""
        root = DirNode()
        current = root

        for lno, raw in enumerate(lines, start=1):
            s = raw.strip()

            # Validation: unterminated header
            if s.startswith("[") and "]" not in s:
                raise DirectiveSyntaxError(
                    f"unterminated context header at line {lno}: missing ']'"
                )

            m = _HEADER_RE.match(s)
            if m:
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

        # Strict validation for dangling value-taking flag at file end:
        # append empty string (compat with legacy tokenizer behavior)
        self.validate(current.tokens)

        return root

    def validate(self, tokens: List[str]) -> None:
        """Apply strict validations and post-processing to *tokens*."""
        if tokens and tokens[-1] in _VALUE_FLAGS:
            tokens.append("")


# --- Backwards-compatible functional API ------------------------------------

def parse_directive_file(path: Path) -> DirNode:
    """Compatibility wrapper returning the root DirNode."""
    return DirectiveParser().parse(path)