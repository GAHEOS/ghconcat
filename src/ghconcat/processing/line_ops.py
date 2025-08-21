import logging
import re
from typing import Iterable, List, Mapping, Optional, Pattern, Tuple

from ghconcat.processing.comment_rules import COMMENT_RULES

CommentRules = Mapping[str, Tuple[Pattern[str], Pattern[str], Optional[Pattern[str]], Optional[Pattern[str]]]]


class LineProcessingService:
    """Line-level operations (slicing and cleaning) used by the walker."""

    def __init__(self, *, comment_rules: CommentRules, line1_re: Pattern[str],
                 logger: Optional[logging.Logger] = None) -> None:
        self._rules = comment_rules
        self._line1_re = line1_re
        self._log = logger or logging.getLogger('ghconcat.lineops')
        self._re_blank = re.compile(r'^\s*$')

    @classmethod
    def create_default(cls, *, line1_re: Pattern[str],
                       logger: Optional[logging.Logger] = None,
                       comment_rules: CommentRules) -> 'LineProcessingService':
        """Factory method for the default instance used across the app."""
        return cls(comment_rules=comment_rules or COMMENT_RULES, line1_re=line1_re, logger=logger)

    def slice_lines(self, raw: List[str], begin: Optional[int], total: Optional[int],
                    keep_header: bool) -> List[str]:
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

    def clean_lines(self, lines: Iterable[str], ext: str, *, rm_comments: bool,
                    no_rm_comments: bool, rm_imp: bool, rm_exp: bool,
                    keep_blank: bool) -> List[str]:
        out: List[str] = []
        rules = self._rules.get(ext.lower())
        simple_rx = rules[0] if rules else None
        full_rx = rules[1] if rules else None
        import_rx = rules[2] if rules else None
        export_rx = rules[3] if rules else None
        for ln in lines:
            if rules:
                if no_rm_comments and full_rx and full_rx.match(ln):
                    continue
                if rm_comments and simple_rx and simple_rx.match(ln):
                    continue
                if rm_imp and import_rx and import_rx.match(ln):
                    continue
                if rm_exp and export_rx and export_rx.match(ln):
                    continue
            if not keep_blank and self._re_blank.match(ln):
                continue
            out.append(ln)
        return out
