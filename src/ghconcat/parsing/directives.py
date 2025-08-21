import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from ghconcat.parsing.attr_sets import _VALUE_FLAGS
from ghconcat.parsing.source import DirectiveSource
from ghconcat.parsing.tokenizer import DirectiveTokenizer


class DirectiveSyntaxError(ValueError):
    """Raised when a directive file contains a structural/syntax error."""
    pass


@dataclass
class DirNode:
    name: Optional[str] = None
    tokens: List[str] = field(default_factory=list)
    children: List['DirNode'] = field(default_factory=list)


_HEADER_RE = re.compile(r'^\s*\[(?P<name>[^\]]*)]\s*$')


class DirectiveParser:
    """Parses directive files into a tree of DirNode instances.

    Backward-compatibility:
        Public behavior is kept intact. This version augments error
        messages with a richer source context (file/line/column) and
        uses DirectiveTokenizer.safe_tokenize_line to avoid raising on
        shlex errors while providing actionable diagnostics.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger('ghconcat.dirparser')

    def parse(self, path: Path) -> DirNode:
        with path.open('r', encoding='utf-8') as fp:
            return self.parse_lines(fp.readlines(), src=DirectiveSource(path=path))

    def parse_lines(self, lines: Iterable[str], src: Optional[DirectiveSource] = None) -> DirNode:
        root = DirNode()
        current = root

        def _finalize(node: DirNode) -> None:
            node.tokens = self.validate(node.tokens)

        for lno, raw in enumerate(lines, start=1):
            s = raw.strip()
            if s.startswith('[') and ']' not in s:
                raise DirectiveSyntaxError(
                    f"unterminated context header at {self._fmt_src(src, lno)}: missing ']'"
                )
            m = _HEADER_RE.match(s)
            if m:
                _finalize(current)
                name = (m.group('name') or '').strip()
                if not name:
                    raise DirectiveSyntaxError(f'empty context name at {self._fmt_src(src, lno)}')
                node = DirNode(name=name)
                root.children.append(node)
                current = node
                continue

            # Tokenize the raw line with context-aware error capture.
            toks, err = DirectiveTokenizer.safe_tokenize_line(
                raw, (src or DirectiveSource()).with_line_col(lno), value_flags=_VALUE_FLAGS
            )
            if err:
                # Non-fatal: we log and continue, preserving previous behavior
                # (tests rely on permissive parsing).
                self._log.warning(err)
            if toks:
                current.tokens.extend(toks)

        _finalize(current)
        return root

    def validate(self, tokens: List[str]) -> List[str]:
        if tokens and tokens[-1] in _VALUE_FLAGS:
            return [*tokens, '']
        return tokens

    @staticmethod
    def _fmt_src(src: Optional[DirectiveSource], line: int | None = None) -> str:
        """Build a human-friendly 'file:line' label."""
        s = (src or DirectiveSource())
        if line is not None:
            s = s.with_line_col(line)
        return s.format()


def parse_directive_file(path: Path) -> DirNode:
    return DirectiveParser().parse(path)