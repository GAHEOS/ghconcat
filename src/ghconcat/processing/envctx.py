import logging
import re
from typing import Callable, Dict, List, Optional, Sequence, Set


class EnvContext:
    """Environment token expansion and CLI KV parsing utilities.

    This helper is responsible for:
    - Collecting environment `VAR=VAL` assignments from CLI tokens.
    - Expanding `$VARNAME` occurrences in tokens using inherited + local env.
    - Supporting a special `none` sentinel to disable value-taking flags.

    All public methods preserve the original behavior to keep tests green.
    """

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        var_pattern: str = r"\$([a-zA-Z_][\w\-]*)",
        assignment_flags: Sequence[str] = ("-e", "--env", "-E", "--global-env"),
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.env")
        self._env_ref = re.compile(var_pattern)
        self._assign_flags: Set[str] = set(assignment_flags)

    def refresh_values(self, env_map: Dict[str, str]) -> None:
        """Resolve nested references in the provided map until stable."""
        changed = True
        while changed:
            changed = False
            for key, val in list(env_map.items()):
                new_val = self._env_ref.sub(lambda m: env_map.get(m.group(1), ""), val)
                if new_val != val:
                    env_map[key] = new_val
                    changed = True

    def collect_from_tokens(
        self,
        tokens: Sequence[str],
        *,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, str]:
        """Collect `-e/--env` and `-E/--global-env` assignments from tokens.

        Returns:
            Dict[str, str]: A map of collected variables.
        """
        env_map: Dict[str, str] = {}
        it = iter(tokens)
        for tok in it:
            if tok in self._assign_flags:
                try:
                    kv = next(it)
                except StopIteration:
                    # Keep behavior but provide a clearer message.
                    self._fatal(f"flag {tok} expects VAR=VAL", on_error)
                    continue
                parsed = self._try_parse_kv_with_flag(tok, kv, on_error=on_error)
                if parsed is None:
                    continue
                key, val = parsed
                env_map[key] = val
        return env_map

    def substitute_in_tokens(self, tokens: List[str], env_map: Dict[str, str]) -> List[str]:
        """Expand `$VARS` in tokens using the provided `env_map`."""
        out: List[str] = []
        skip_value = False
        for tok in tokens:
            if skip_value:
                out.append(tok)
                skip_value = False
                continue
            if tok in self._assign_flags:
                out.append(tok)
                skip_value = True
                continue
            out.append(self._env_ref.sub(lambda m: env_map.get(m.group(1), ""), tok))
        return out

    def strip_none(
        self,
        tokens: List[str],
        *,
        value_flags: Set[str],
        none_value: str,
    ) -> List[str]:
        """Remove any flag followed by the `none` sentinel, plus its value slot."""
        disabled: Set[str] = set()
        i = 0
        while i + 1 < len(tokens):
            if tokens[i] in value_flags and tokens[i + 1].lower() == none_value:
                disabled.add(tokens[i])
                i += 2
            else:
                i += 1
        cleaned: List[str] = []
        skip_next = False
        for tok in tokens:
            if skip_next:
                skip_next = False
                continue
            if tok in value_flags and tok in disabled:
                skip_next = True
                continue
            cleaned.append(tok)
        return cleaned

    def parse_items(
        self,
        items: Optional[List[str]],
        *,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, str]:
        """Parse a list of `VAR=VAL` items (e.g., from `--env` group)."""
        env_map: Dict[str, str] = {}
        for itm in items or []:
            parsed = self._try_parse_kv(itm, on_error=on_error)
            if parsed is None:
                continue
            key, val = parsed
            env_map[key] = val
        return env_map

    def expand_tokens(
        self,
        tokens: List[str],
        inherited_env: Dict[str, str],
        *,
        value_flags: Set[str],
        none_value: str,
    ) -> List[str]:
        """Expand tokens by applying env inheritance, substitution and `none` stripping.

        Steps:
        1) Merge inherited env with local assignments found in `tokens`.
        2) Resolve nested references (`$VAR`) within the env map.
        3) Substitute `$VAR` occurrences inside the tokens themselves.
        4) Remove any `flag none` pairs for flags in `value_flags`.
        """
        env_all: Dict[str, str] = {
            **inherited_env,
            **self.collect_from_tokens(tokens),
        }
        self.refresh_values(env_all)
        expanded = self.substitute_in_tokens(tokens, env_all)
        return self.strip_none(expanded, value_flags=value_flags, none_value=none_value)

    def _fatal(self, msg: str, on_error: Optional[Callable[[str], None]]) -> None:
        """Internal error dispatcher honoring the provided `on_error` callback."""
        if on_error is not None:
            on_error(msg)
        else:
            raise ValueError(msg)

    # ----------------------------
    # Internal helpers (deduped)
    # ----------------------------

    def _try_parse_kv(
        self,
        raw: str,
        *,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Optional[tuple[str, str]]:
        """Parse a generic `VAR=VAL` expression."""
        if "=" not in raw:
            self._fatal(f"--env expects VAR=VAL (got '{raw}')", on_error)
            return None
        key, val = raw.split("=", 1)
        return key, val

    def _try_parse_kv_with_flag(
        self,
        flag: str,
        raw: str,
        *,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> Optional[tuple[str, str]]:
        """Parse `VAR=VAL` but tailor error message for a specific flag."""
        if "=" not in raw:
            self._fatal(f"{flag} expects VAR=VAL (got '{raw}')", on_error)
            return None
        key, val = raw.split("=", 1)
        return key, val