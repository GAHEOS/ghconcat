import logging
import re
from typing import Optional, Sequence, Tuple


class TextTransformer:
    """Parse and apply text replacement specifications.

    This class extracts the legacy ghconcat text substitution logic from the
    monolithic module and exposes it behind an injectable API suitable for
    direct unit testing and reuse.

    Design goals
    ------------
    • 1:1 behavioral compatibility with the previous _parse_replace_spec and
      _apply_replacements functions.
    • Pluggable delimiter for regex specs (default '/'), although ghconcat
      uses '/' and tests rely on it.
    • Non‑fatal error handling: invalid specs are logged at WARNING level
      and silently ignored (as before).

    Parameters
    ----------
    logger:
        Optional logger instance for consistent log format.
    regex_delim:
        Single-character delimiter used to split /pattern/repl/flags. The
        default ('/') matches ghconcat's legacy behavior.
    """

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        regex_delim: str = "/",
    ) -> None:
        if not isinstance(regex_delim, str) or len(regex_delim) != 1:
            raise ValueError("regex_delim must be a single character string")
        self._log = logger or logging.getLogger("ghconcat.textops")
        self._delim = regex_delim

    def parse_replace_spec(
        self,
        spec: str,
    ) -> Optional[Tuple[re.Pattern[str], str, bool]]:
        """Parse a `-y/-Y` SPEC and return (regex, replacement, global_flag).

        Syntax
        ------
        `/pattern/`             → delete (replacement = ''), global=True
        `/pattern/repl/flags`   → replace, flags ∈ {g,i,m,s}

        Escaping:
        The delimiter may be escaped inside parts with '\\/' (when using '/' as
        delimiter). The parser walks the string character-by-character to honor
        escapes precisely (legacy semantics).

        Quotes:
        Leading and trailing single/double quotes around the entire spec are
        stripped when present (e.g., "'/foo/bar/i'").

        Parameters
        ----------
        spec:
            Raw SPEC string exactly as provided to the CLI.

        Returns
        -------
        Optional[Tuple[Pattern[str], str, bool]]
            Compiled regex, replacement text, and whether the 'g' (global)
            flag was present. Returns None on invalid syntax or compilation
            errors; such conditions are logged and ignored by callers.
        """
        if (spec.startswith(("'", '"')) and spec.endswith(spec[0]) and len(spec) >= 2):
            spec = spec[1:-1]

        if not spec.startswith(self._delim):
            self._log.warning("⚠  invalid replace spec (missing leading /): %r", spec)
            return None

        parts: list[str] = []
        buf: list[str] = []
        escaped = False
        delim = self._delim

        for ch in spec[1:]:  # skip first delimiter
            if escaped:
                buf.append(ch)
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == delim:  # unescaped delimiter → new part
                parts.append("".join(buf))
                buf = []
                continue
            buf.append(ch)
        parts.append("".join(buf))  # tail (flags or empty)

        if len(parts) not in {2, 3}:  # pattern / [replacement] / [flags]
            self._log.warning("⚠  invalid replace spec: %r", spec)
            return None

        pattern_src = parts[0]
        replacement = "" if len(parts) == 2 else parts[1]
        flags_src = parts[-1] if len(parts) == 3 else "g"

        re_flags = 0
        global_sub = "g" in flags_src
        if "i" in flags_src:
            re_flags |= re.IGNORECASE
        if "m" in flags_src:
            re_flags |= re.MULTILINE
        if "s" in flags_src:
            re_flags |= re.DOTALL

        try:
            regex = re.compile(pattern_src, flags=re_flags)
        except re.error as exc:
            self._log.warning("⚠  invalid regex in spec %r: %s", spec, exc)
            return None

        return regex, replacement, global_sub

    def apply_replacements(
        self,
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
    ) -> str:
        """Apply *replace_specs* to *text*, protecting *preserve_specs* regions.

        The algorithm follows the legacy ghconcat behavior:

          1) Parse every replacement spec; invalid ones are ignored.
          2) Parse preserve specs (regex only) and temporarily shield matches
             by replacing them with sentinel tokens.
          3) Apply replacements. For each rule:
               • If the 'g' flag is present → `count=0` (global).
               • Otherwise → single substitution (`count=1`).
          4) Restore shielded regions.

        Parameters
        ----------
        text:
            Original input text.
        replace_specs:
            Sequence of `/pattern/repl/flags` specs (or delete form `/pattern/`).
        preserve_specs:
            Sequence of `/pattern/flags` specs acting as exceptions.

        Returns
        -------
        str
            The transformed text. If `replace_specs` is empty or all specs are
            invalid, *text* is returned unchanged.
        """
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
                preserve_rules.append(parsed[0])  # only regex part needed

        if not replace_rules:
            return text

        placeholders: dict[str, str] = {}

        def _shield(match: re.Match[str]) -> str:
            token = f"\x00GHPRS{len(placeholders)}\x00"
            placeholders[token] = match.group(0)
            return token

        for rx in preserve_rules:
            text = rx.sub(_shield, text)

        for rx, repl, is_global in replace_rules:
            count = 0 if is_global else 1
            text = rx.sub(repl, text, count=count)

        for token, original in placeholders.items():
            text = text.replace(token, original)

        return text