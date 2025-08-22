from __future__ import annotations
from pathlib import Path
from typing import List, Tuple

from ghconcat.core.interfaces.engine import ExecutionEngineProtocol
from ghconcat.core.models import ContextConfig
from ghconcat.core.report import ExecutionReport
from ghconcat.cli import GhConcat
from ghconcat.runtime.sdk import _call_openai
from ghconcat.runtime.wiring import build_engine_config, build_engine
from ghconcat.logging.helpers import get_logger


class EngineRunner(ExecutionEngineProtocol):
    def __init__(self, *, logger=None) -> None:
        self._log = logger or get_logger("runner")

    def _to_argv(self, ctx: ContextConfig) -> List[str]:
        from ghconcat.runtime.flag_mapping import context_to_argv  # local import
        return context_to_argv(ctx)

    def run(self, ctx: ContextConfig) -> str:
        argv = self._to_argv(ctx)
        return GhConcat.run(argv)

    def run_with_report(self, ctx: ContextConfig) -> Tuple[str, ExecutionReport]:
        _seen_files: set[str] = set()
        _clones_cache: dict[tuple[str, str | None], Path] = {}
        _workspaces_seen: set[Path] = set()

        cfg = build_engine_config(
            logger=self._log,
            header_delim="===== ",
            seen_files=_seen_files,
            clones_cache=_clones_cache,
            workspaces_seen=_workspaces_seen,
            fatal_handler=lambda msg: (_ for _ in ()).throw(SystemExit(msg)),
        )
        engine = build_engine(cfg, call_openai=_call_openai)

        out = engine.run(ctx)
        return (out, engine._report)