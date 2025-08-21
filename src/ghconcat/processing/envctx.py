import logging
import re
from typing import Callable, Dict, List, Optional, Sequence, Set

from ghconcat.logging.helpers import get_logger


class EnvContext:
    def __init__(
            self,
            *,
            logger: Optional[logging.Logger] = None,
            var_pattern: str = r'\$([a-zA-Z_][\w\-]*)',
            assignment_flags: Sequence[str] = ('-e', '--env', '-E', '--global-env'),
    ) -> None:
        self._log = logger or get_logger('processing.env')
        self._env_ref = re.compile(var_pattern)
        self._assign_flags: Set[str] = set(assignment_flags)

    def _fatal(self, msg: str, on_error: Optional[Callable[[str], None]]) -> None:
        if on_error is not None:
            on_error(msg)
        else:
            raise ValueError(msg)

    def _iter_assignment_pairs(self, tokens: Sequence[str]) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        it = iter(tokens)
        for tok in it:
            if tok in self._assign_flags:
                try:
                    kv = next(it)
                except StopIteration:
                    self._fatal(f'flag {tok} expects VAR=VAL', None)
                    break
                pairs.append((tok, kv))
        return pairs

    def refresh_values(self, env_map: Dict[str, str]) -> None:
        changed = True
        while changed:
            changed = False
            for key, val in list(env_map.items()):
                new_val = self._env_ref.sub(lambda m: env_map.get(m.group(1), ''), val)
                if new_val != val:
                    env_map[key] = new_val
                    changed = True

    def collect_from_tokens(self, tokens: Sequence[str], *, on_error: Optional[Callable[[str], None]] = None) -> Dict[
        str, str]:
        env_map: Dict[str, str] = {}
        for flag, kv in self._iter_assignment_pairs(tokens):
            if '=' not in kv:
                self._fatal(f"{flag} expects VAR=VAL (got '{kv}')", on_error)
                continue
            key, val = kv.split('=', 1)
            env_map[key] = val
        return env_map

    def substitute_in_tokens(self, tokens: List[str], env_map: Dict[str, str]) -> List[str]:
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
            out.append(self._env_ref.sub(lambda m: env_map.get(m.group(1), ''), tok))
        return out

    def strip_none(self, tokens: List[str], *, value_flags: Set[str], none_value: str) -> List[str]:
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

    def parse_items(self, items: Optional[List[str]], *, on_error: Optional[Callable[[str], None]] = None) -> Dict[
        str, str]:
        env_map: Dict[str, str] = {}
        for itm in items or []:
            if '=' not in itm:
                self._fatal(f"--env expects VAR=VAL (got '{itm}')", on_error)
                continue
            key, val = itm.split('=', 1)
            env_map[key] = val
        return env_map

    def expand_tokens(self, tokens: List[str], inherited_env: Dict[str, str], *, value_flags: Set[str],
                      none_value: str) -> List[str]:
        env_all: Dict[str, str] = {**inherited_env, **self.collect_from_tokens(tokens)}
        self.refresh_values(env_all)
        expanded = self.substitute_in_tokens(tokens, env_all)
        return self.strip_none(expanded, value_flags=value_flags, none_value=none_value)
