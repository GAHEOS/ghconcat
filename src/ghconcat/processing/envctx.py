import logging
import re
from typing import Callable, Dict, List, Optional, Sequence, Set


class EnvContext:
    """Environment/variables expansion engine for ghconcat.

    This class encapsulates the logic to:
      • Collect `-e/--env` and `-E/--global-env` assignments from CLI tokens.
      • Perform deep `$VAR` interpolation among environment values themselves.
      • Substitute `$VAR` occurrences across CLI tokens (skipping immediate
        values of `-e/-E` so that definitions remain literal).
      • Remove any flag whose value is the literal `"none"` (case-insensitive).

    The implementation is strictly compatible with the legacy functions
    previously embedded in the monolith, but now packaged for reuse and
    unit testing.

    Parameters
    ----------
    logger:
        Optional logger used for warnings; fatal conditions are reported
        through the provided `on_error` callbacks in public methods.
    var_pattern:
        Regex pattern capturing a single group with the variable name.
        The default matches `$NAME` where `NAME` is `[A-Za-z_][\\w-]*`.
    assignment_flags:
        Flags whose *next* token is an environment assignment (`VAR=VAL`).
        Values following these flags are preserved verbatim during token
        substitution to avoid double-expansion of definitions.
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

    # ---------- Public API ----------

    def refresh_values(self, env_map: Dict[str, str]) -> None:
        """Expand `$V` references inside *env_map* until stable.

        Parameters
        ----------
        env_map:
            Mapping of environment keys to (possibly referencing) values.

        Notes
        -----
        The method updates *env_map* **in place**.
        """
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
        """Collect `VAR=VAL` assignments following `-e/-E` flags.

        Parameters
        ----------
        tokens:
            CLI-like token sequence.
        on_error:
            Callback invoked with an error message when malformed input is
            detected (missing value or `VAR=VAL` without `=`). If not provided,
            a `ValueError` is raised instead.

        Returns
        -------
        Dict[str, str]
            A mapping with the collected assignments.
        """
        env_map: Dict[str, str] = {}
        it = iter(tokens)
        for tok in it:
            if tok in self._assign_flags:
                try:
                    kv = next(it)
                except StopIteration:
                    self._fatal("flag {tok} expects VAR=VAL", on_error)
                    continue
                if "=" not in kv:
                    self._fatal(f"{tok} expects VAR=VAL (got '{kv}')", on_error)
                    continue
                key, val = kv.split("=", 1)
                env_map[key] = val
        return env_map

    def substitute_in_tokens(
        self,
        tokens: List[str],
        env_map: Dict[str, str],
    ) -> List[str]:
        """Substitute `$VAR` occurrences across *tokens*.

        Values that immediately follow `-e/-E` are **not** substituted.

        Parameters
        ----------
        tokens:
            CLI-like token list.
        env_map:
            Variable mapping to use for `$VAR` replacement.

        Returns
        -------
        List[str]
            New token list with substitutions applied.
        """
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
        """Remove any flag and its value when the value equals *none_value*.

        Behavior matches the legacy `_strip_none()`:
          1) First pass records **all** flags whose next value equals *none_value*
             (case-insensitive).
          2) Second pass skips **every** occurrence of such flags, removing
             both the flag and its immediate value.

        Parameters
        ----------
        tokens:
            Token list to filter.
        value_flags:
            Set of flags that expect a following value.
        none_value:
            Sentinel (e.g., "none") that disables the flag.

        Returns
        -------
        List[str]
            Filtered tokens.
        """
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
        """Parse a homogeneous list of `VAR=VAL` items into a dict.

        Parameters
        ----------
        items:
            A list of strings each expected as `VAR=VAL`. `None` yields `{}`.
        on_error:
            Callback used to report malformed entries. If absent, a
            `ValueError` is raised.

        Returns
        -------
        Dict[str, str]
            Parsed mapping.
        """
        env_map: Dict[str, str] = {}
        for itm in items or []:
            if "=" not in itm:
                self._fatal(f"--env expects VAR=VAL (got '{itm}')", on_error)
                continue
            key, val = itm.split("=", 1)
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
        """Full expansion pipeline for a directive line.

        Steps (1:1 with legacy semantics):
          1) Collect `-e/-E` assignments into a working env map, seeded by
             *inherited_env*.
          2) Deep-expand `$VAR` inside env values until stable.
          3) Substitute `$VAR` across *tokens*, skipping immediate values
             after `-e/-E`.
          4) Remove any flag whose value is the literal *none_value*.

        Parameters
        ----------
        tokens:
            Input token list.
        inherited_env:
            Variables visible to this context before local `-e`/`-E`.
        value_flags:
            Flags expecting a value (used by the step #4).
        none_value:
            Disabling sentinel (e.g. `"none"`).

        Returns
        -------
        List[str]
            Expanded token list.
        """
        env_all: Dict[str, str] = {**inherited_env, **self.collect_from_tokens(tokens)}
        self.refresh_values(env_all)
        expanded = self.substitute_in_tokens(tokens, env_all)
        return self.strip_none(expanded, value_flags=value_flags, none_value=none_value)

    # ---------- Internals ----------

    def _fatal(self, msg: str, on_error: Optional[Callable[[str], None]]) -> None:
        """Route fatal errors to the provided callback or raise ValueError."""
        if on_error is not None:
            on_error(msg)
        else:
            raise ValueError(msg)