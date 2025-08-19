from typing import Protocol
from ghconcat.core.models import ContextConfig, ExecutionReport

class ExecutionEngineProtocol(Protocol):
    """Top-level orchestration entrypoint (discover → read → transform → render)."""
    def run(self, ctx: ContextConfig) -> str: ...
    def run_with_report(self, ctx: ContextConfig) -> tuple[str, ExecutionReport]: ...