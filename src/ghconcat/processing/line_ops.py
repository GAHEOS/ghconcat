"""
line_ops – Line slicing and cleaning utilities for ghconcat.

This module provides a dedicated service that encapsulates:
  • slice_lines(...) – range slicing with optional header retention.
  • clean_lines(...) – comment/import/export/blank filtering by suffix.

It now also exposes a small factory function that wires the shared
COMMENT_RULES from ghconcat.comment_rules to avoid duplication.
"""

import logging
import re
from typing import Iterable, List, Mapping, Optional, Pattern, Tuple

from ghconcat.processing.comment_rules import COMMENT_RULES as DEFAULT_COMMENT_RULES


CommentRules = Mapping[str, Tuple[
    Pattern[str],            # simple comment
    Pattern[str],            # full-line comment
    Optional[Pattern[str]],  # import-like
    Optional[Pattern[str]],  # export-like
]]


class LineProcessingService:
    """Stateless line-processing utilities with DI-friendly dependencies.

    Parameters
    ----------
    comment_rules:
        Mapping of file suffixes to comment/import/export regex tuples.
    line1_re:
        Compiled regex used by the special "line 1" pruning rule.
    logger:
        Optional logger for homogeneous logs; it is not used for control flow.
    """

    def __init__(
        self,
        *,
        comment_rules: CommentRules,
        line1_re: Pattern[str],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._rules = comment_rules
        self._line1_re = line1_re
        self._log = logger or logging.getLogger("ghconcat.lineops")

    def slice_lines(
        self,
        raw: List[str],
        begin: Optional[int],
        total: Optional[int],
        keep_header: bool,
    ) -> List[str]:
        """Return a sliced view of *raw* honoring header rules."""
        if not raw:
            return []

        start = max(1, begin or 1)
        end_excl = start - 1 + (total or len(raw) - start + 1)
        segment = raw[start - 1:end_excl]

        if keep_header and start > 1:
            segment = [raw[0], *segment]

        if not keep_header and start > 1:
            segment = [ln for ln in segment if not self._line1_re.match(ln)]

        return segment

    def clean_lines(
        self,
        lines: Iterable[str],
        ext: str,
        *,
        rm_simple: bool,
        rm_all: bool,
        rm_imp: bool,
        rm_exp: bool,
        keep_blank: bool,
    ) -> List[str]:
        """Apply comment/import/export/blank filtering to *lines*."""
        out: List[str] = []
        rules = self._rules.get(ext.lower())

        simple_rx = rules[0] if rules else None
        full_rx = rules[1] if rules else None
        import_rx = rules[2] if rules else None
        export_rx = rules[3] if rules else None

        re_blank = re.compile(r"^\s*$")

        for ln in lines:
            if rules:
                if rm_all and full_rx and full_rx.match(ln):
                    continue
                if rm_simple and simple_rx and simple_rx.match(ln):
                    continue
                if rm_imp and import_rx and import_rx.match(ln):
                    continue
                if rm_exp and export_rx and export_rx.match(ln):
                    continue

            if not keep_blank and re_blank.match(ln):
                continue

            out.append(ln)

        return out


def create_default_line_ops(
    *,
    line1_re: Pattern[str],
    logger: Optional[logging.Logger] = None,
) -> LineProcessingService:
    """Return a LineProcessingService wired to the shared COMMENT_RULES.

    This small factory avoids rule duplication and is safe to use across
    the process since it keeps no mutable state internally.
    """
    return LineProcessingService(
        comment_rules=DEFAULT_COMMENT_RULES,
        line1_re=line1_re,
        logger=logger,
    )