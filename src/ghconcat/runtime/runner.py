from __future__ import annotations
"""
Thin EngineRunner that satisfies ExecutionEngineProtocol.

This runner maps a ContextConfig into the canonical GhConcat flow.
Uses class-based helpers (TextReplacer, EnvExpander, NamespaceMerger).
"""
import re
from pathlib import Path
from typing import List, Tuple

from ghconcat.core.interfaces.engine import ExecutionEngineProtocol
from ghconcat.core.models import ContextConfig
from ghconcat.core.report import ExecutionReport
from ghconcat.cli import GhConcat
from ghconcat.constants import HEADER_DELIM
from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.runtime.sdk import _call_openai
from ghconcat.utils.net import ssl_context_for as _ssl_ctx_for
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.parsing.parser import _build_parser
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.runtime.helpers import TextReplacer, EnvExpander, NamespaceMerger
from ghconcat.logging.helpers import get_logger


class EngineRunner(ExecutionEngineProtocol):
    def __init__(self, *, logger=None) -> None:
        self._log = logger or get_logger('runner')

    def _to_argv(self, ctx: ContextConfig) -> List[str]:
        args: List[str] = []
        args += ['-w', str(ctx.cwd)]
        if ctx.workspace:
            args += ['-W', str(ctx.workspace)]
        for p in ctx.include or ():
            args += ['-a', str(p)]
        for p in ctx.exclude or ():
            args += ['-A', str(p)]
        for k, v in (ctx.flags or {}).items():
            if isinstance(v, bool):
                if v:
                    args.append(str(k))
            elif v is not None:
                args += [str(k), str(v)]
        for k, v in (ctx.env or {}).items():
            args += ['-E', f'{k}={v}']
        return args

    def run(self, ctx: ContextConfig) -> str:
        argv = self._to_argv(ctx)
        return GhConcat.run(argv)

    def run_with_report(self, ctx: ContextConfig) -> Tuple[str, ExecutionReport]:
        _line1_re = re.compile(r'^\s*#\s*line\s*1\d*\s*$')
        _seen_files: set[str] = set()
        _clones_cache: dict[tuple[str, str | None], Path] = {}
        _workspaces_seen: set[Path] = set()
        _line_ops = LineProcessingService(comment_rules=COMMENT_RULES, line1_re=_line1_re, logger=self._log)
        replacer = TextReplacer(logger=self._log)
        envx = EnvExpander(logger=self._log)
        merger = NamespaceMerger(logger=self._log)

        cfg = EngineConfig(
            logger=self._log,
            header_delim=HEADER_DELIM,
            seen_files=_seen_files,
            clones_cache=_clones_cache,
            workspaces_seen=_workspaces_seen,
            ssl_ctx_provider=_ssl_ctx_for,
            parser_factory=_build_parser,
            post_parse=merger.post_parse,
            merge_ns=merger.merge,
            expand_tokens=envx.expand_tokens,
            parse_env_items=envx.parse_items,
            interpolate=lambda tpl, m: StringInterpolator().interpolate(tpl, m),
            apply_replacements=replacer.apply,
            slice_lines=_line_ops.slice_lines,
            clean_lines=_line_ops.clean_lines,
            fatal=lambda msg: (_ for _ in ()).throw(SystemExit(msg)),
            classifier=None,
        )
        builder = EngineBuilder.from_config(cfg)
        engine = builder.build(call_openai=_call_openai)
        out = engine.run(ctx)
        return (out, engine._report)