# src/ghconcat/processing/line_ops.py
import logging
import re
from typing import Iterable, List, Mapping, Optional, Pattern, Tuple
from ghconcat.logging.helpers import get_logger

CommentRules = Mapping[str, Tuple[Pattern[str], Pattern[str], Optional[Pattern[str]], Optional[Pattern[str]]]]


class LineProcessingService:
    """Line processing helpers (slicing and regex-based cleaning).

    This class is intentionally minimal; language-aware cleaners live in
    `LanguageCleanerRegistry` and are invoked upstream when available.
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
        self._log = logger or get_logger('processing.lineops')
        self._re_blank = re.compile(r'^\s*$')

    def slice_lines(
        self,
        raw: List[str],
        begin: Optional[int],
        total: Optional[int],
        keep_header: bool,
    ) -> List[str]:
        """Return a sliced view of the input lines honoring header policy."""
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
        rm_comments: bool,
        no_rm_comments: bool,
        rm_imp: bool,
        rm_exp: bool,
        keep_blank: bool,
    ) -> List[str]:
        """Apply regex-based cleaning according to per-language rules.

        Args:
            lines: Input lines (with trailing newlines preserved).
            ext: File suffix in lowercase (e.g. ".py").
            rm_comments: Enable simple comment removal.
            no_rm_comments: If True, remove *all* comments instead of the simple rule.
            rm_imp: Remove import/use/include-like statements when available.
            rm_exp: Remove export/module.exports-like statements when available.
            keep_blank: Preserve blank lines.

        Returns:
            A list of cleaned lines.
        """
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