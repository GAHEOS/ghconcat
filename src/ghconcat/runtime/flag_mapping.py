# src/ghconcat/runtime/flag_mapping.py
from __future__ import annotations
"""Mapping layer from high-level ContextConfig.flags to CLI argv tokens.

Back-compat policy:
- We keep the current mapping intact to avoid breaking callers.
- Two helper utilities are provided to audit and prune:
    * get_supported_flag_specs()
    * simplify_for_parser(parser)
- NEW: `context_to_argv(ctx)` centralizes ContextConfig → argv building
  so both ExecutionEngine and EngineRunner share the exact logic.
"""
from typing import Any, Iterable, List, Mapping
from ghconcat.core.models import ContextConfig

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
    """Convert a mapping of flags to argv tokens preserving current semantics."""
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


def get_supported_flag_specs() -> dict[str, tuple[str, type]]:
    """Return a copy of the flag specs for auditing."""
    return dict(_FLAG_SPECS)


def simplify_for_parser(parser) -> dict[str, tuple[str, type]]:
    """Return a pruned dict limited to the parser .dest names."""
    try:
        actions = getattr(parser, '_actions', [])
        dests = {getattr(a, 'dest', None) for a in actions}
        dests.discard(None)
    except Exception:
        return get_supported_flag_specs()
    return {k: v for k, v in _FLAG_SPECS.items() if k in dests}


def context_to_argv(ctx: ContextConfig) -> List[str]:
    """Build argv tokens from a ContextConfig (single source of truth).

    The order matches the previous behavior to remain test-stable:
    -w/-W, then -a/-A, then mapped flags, and finally -E VAR=VAL.
    """
    args: List[str] = ['-w', str(ctx.cwd)]
    if ctx.workspace:
        args += ['-W', str(ctx.workspace)]
    for p in ctx.include or ():
        args += ['-a', str(p)]
    for p in ctx.exclude or ():
        args += ['-A', str(p)]
    args += flags_to_argv(ctx.flags)
    for k, v in (ctx.env or {}).items():
        args += ['-E', f'{k}={v}']
    return args


__all__ = [
    'flags_to_argv',
    'get_supported_flag_specs',
    'simplify_for_parser',
    'context_to_argv',
]