from __future__ import annotations
"""Mapping layer from high-level ContextConfig.flags to CLI argv tokens.

Back-compat policy:
- We keep the current mapping intact to avoid breaking callers.
- Two helper utilities are provided to *audit and prune* unused flags when
  running end-to-end with `ContextConfig` + `EngineRunner.run_with_report`:
    * get_supported_flag_specs()  → returns a copy of the current specs
    * simplify_for_parser(parser) → returns a pruned dict limited to parser dests

This allows advanced integrations to reduce the wiring without touching
existing tests or public behavior.
"""

from typing import Any, Iterable, List, Mapping

_FLAG_SPECS: dict[str, tuple[str, type]] = {
    'url_depth': ('--url-depth', int),
    'url_cross_domain': ('--url-allow-cross-domain', bool),
    'suffix': ('-s', list),
    'exclude_suf': ('-S', list),
    'total_lines': ('-n', int),
    'first_line': ('-N', int),
    'keep_first_line': ('-m', bool),
    'no_first_line': ('-M', bool),
    'replace_rules': ('-y', list),
    'preserve_rules': ('-Y', list),
    'rm_comments': ('-c', bool),
    'no_rm_comments': ('-C', bool),
    'rm_import': ('-i', bool),
    'rm_export': ('-I', bool),
    'strip_blank': ('-b', bool),
    'keep_blank': ('-B', bool),
    'strip_html': ('-K', bool),
    'template': ('-t', str),
    'child_template': ('-T', str),
    'output': ('-o', str),
    'to_stdout': ('-O', bool),
    'wrap_lang': ('-u', str),
    'unwrap': ('-U', bool),
    'headers': ('-h', bool),
    'no_headers': ('-H', bool),
    'relative_path': ('-r', bool),
    'absolute_path': ('-R', bool),
    'list_only': ('-l', bool),
    'no_list': ('-L', bool),
    'env_vars': ('-e', list),
    'global_env': ('-E', list),
    'ai': ('--ai', bool),
    'ai_model': ('--ai-model', str),
    'ai_temperature': ('--ai-temperature', float),
    'ai_top_p': ('--ai-top-p', float),
    'ai_presence_penalty': ('--ai-presence-penalty', float),
    'ai_frequency_penalty': ('--ai-frequency-penalty', float),
    'ai_system_prompt': ('--ai-system-prompt', str),
    'ai_seeds': ('--ai-seeds', str),
    'ai_max_tokens': ('--ai-max-tokens', int),
    'ai_reasoning_effort': ('--ai-reasoning-effort', str),
    'preserve_cache': ('--preserve-cache', bool),
    'upgrade': ('--upgrade', bool),
    'json_logs': ('--json-logs', bool),
    'classifier_ref': ('--classifier', str),
    'classifier_policies': ('--classifier-policies', str),
}


def _as_iter(val: Any) -> Iterable[Any]:
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return val
    return [val]


def flags_to_argv(flags: Mapping[str, Any] | None) -> List[str]:
    """Convert a ContextConfig.flags mapping to CLI argv tokens.

    Backward-compatible; ignores unknown keys silently.
    """
    if not flags:
        return []
    argv: List[str] = []
    for key, val in flags.items():
        spec = _FLAG_SPECS.get(key)
        if not spec:
            continue
        cli_flag, kind = spec
        if kind is bool:
            if bool(val):
                argv.append(cli_flag)
            continue
        if kind is list:
            for item in _as_iter(val):
                argv += [cli_flag, str(item)]
            continue
        if val is not None:
            argv += [cli_flag, str(val)]
    return argv


# ---- New: helpers for auditing/simplifying the mapping ---------------------


def get_supported_flag_specs() -> dict[str, tuple[str, type]]:
    """Return a shallow copy of the current flag specs (for auditing)."""
    return dict(_FLAG_SPECS)


def simplify_for_parser(parser) -> dict[str, tuple[str, type]]:
    """Return a pruned mapping limited to the given argparse parser.

    The function reads the parser's known destinations and filters the
    internal mapping to the subset of flags that are *actually* present.
    It is safe to use in advanced DI flows without affecting global tests.
    """
    try:
        actions = getattr(parser, '_actions', [])  # std argparse API
        dests = {getattr(a, 'dest', None) for a in actions}
        dests.discard(None)
    except Exception:
        return get_supported_flag_specs()
    return {k: v for k, v in _FLAG_SPECS.items() if k in dests}