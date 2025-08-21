from __future__ import annotations

"""
Protocol describing a minimal execution surface for engine runners.

NOTE:
    The runtime uses a richer engine implementation internally. This
    protocol is implemented by a thin EngineRunner that maps a
    ContextConfig into the CLI-compatible execution flow.
"""

from typing import Protocol
from ghconcat.core.models import ContextConfig
from ghconcat.core.report import ExecutionReport


class ExecutionEngineProtocol(Protocol):
    def run(self, ctx: ContextConfig) -> str:
        ...

    def run_with_report(self, ctx: ContextConfig) -> tuple[str, ExecutionReport]:
        ...