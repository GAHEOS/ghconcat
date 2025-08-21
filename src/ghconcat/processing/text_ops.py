import logging
import re
from typing import Optional, Sequence, Tuple

from ghconcat.logging.helpers import get_logger


class TextTransformer:
    def __init__(self, *, logger: Optional[logging.Logger] = None, regex_delim: str = '/') -> None:
        """Regex-driven text replacement with preserve support."""
        if not isinstance(regex_delim, str) or len(regex_delim) != 1:
            raise ValueError('regex_delim must be a single character string')
        self._log = logger or get_logger('processing.textops')
        self._delim = regex_delim

    def parse_replace_spec(self, spec: str) -> Optional[Tuple[re.Pattern[str], str, bool]]:
        if spec.startswith(("'", '"')) and spec.endswith(spec[0]) and (len(spec) >= 2):
            spec = spec[1:-1]
        if not spec.startswith(self._delim):
            self._log.warning('⚠  invalid replace spec (missing leading /): %r', spec)
            return None

        parts: list[str] = []
        buf: list[str] = []
        escaped = False
        delim = self._delim
        for ch in spec[1:]:
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == '\\':
                escaped = True
                continue
            if ch == delim:
                parts.append(''.join(buf))
                buf = []
                continue
            buf.append(ch)
        parts.append(''.join(buf))

        if len(parts) not in {2, 3}:
            self._log.warning('⚠  invalid replace spec: %r', spec)
            return None

        pattern_src = parts[0]
        replacement = '' if len(parts) == 2 else parts[1]
        flags_src = parts[-1] if len(parts) == 3 else 'g'

        re_flags = 0
        global_sub = 'g' in flags_src
        if 'i' in flags_src:
            re_flags |= re.IGNORECASE
        if 'm' in flags_src:
            re_flags |= re.MULTILINE
        if 's' in flags_src:
            re_flags |= re.DOTALL

        try:
            regex = re.compile(pattern_src, flags=re_flags)
        except re.error as exc:
            self._log.warning('⚠  invalid regex in spec %r: %s', spec, exc)
            return None

        return (regex, replacement, global_sub)

    def apply_replacements(self, text: str, replace_specs: Sequence[str] | None,
                           preserve_specs: Sequence[str] | None) -> str:
        if not replace_specs:
            return text

        replace_rules: list[Tuple[re.Pattern[str], str, bool]] = []
        for spec in replace_specs:
            parsed = self.parse_replace_spec(spec)
            if parsed:
                replace_rules.append(parsed)

        preserve_rules: list[re.Pattern[str]] = []
        for spec in preserve_specs or []:
            parsed = self.parse_replace_spec(spec)
            if parsed:
                preserve_rules.append(parsed[0])

        if not replace_rules:
            return text

        placeholders: dict[str, str] = {}

        def _shield(match: re.Match[str]) -> str:
            token = f'\x00GHPRS{len(placeholders)}\x00'
            placeholders[token] = match.group(0)
            return token

        # Shield preserve regions
        for rx in preserve_rules:
            text = rx.sub(_shield, text)

        # Apply replacements
        for rx, repl, is_global in replace_rules:
            count = 0 if is_global else 1
            text = rx.sub(repl, text, count=count)

        # Restore shielded regions
        for token, original in placeholders.items():
            text = text.replace(token, original)

        return text
