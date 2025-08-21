from __future__ import annotations

"""
Detailed runtime execution report.

New (opt-in) AI token metrics:
- ai_tokens_in: Optional[int]
- ai_tokens_out: Optional[int]
- ai_model_ctx_window: Optional[int]

New in this refactor (best-effort real metrics if available):
- ai_finish_reason: Optional[str]
- ai_usage_prompt: Optional[int]
- ai_usage_completion: Optional[int]
- ai_usage_total: Optional[int]

These fields are filled only when --ai is used and data is available.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ExecutionReport:
    started_at: float = field(default_factory=time.perf_counter)
    finished_at: float | None = None
    duration_s: float | None = None

    contexts: int = 0

    files_total: int = 0
    files_by_source: Dict[str, int] = field(
        default_factory=lambda: {"local": 0, "git": 0, "url": 0, "scrape": 0}
    )

    bytes_total: int = 0
    bytes_by_source: Dict[str, int] = field(
        default_factory=lambda: {"local": 0, "git": 0, "url": 0, "scrape": 0}
    )

    time_by_stage: Dict[str, float] = field(
        default_factory=lambda: {
            "local_discovery": 0.0,
            "git_collect": 0.0,
            "url_fetch": 0.0,
            "url_scrape": 0.0,
            "concat": 0.0,
            "template": 0.0,
            "ai": 0.0,
        }
    )

    roots: List[str] = field(default_factory=list)
    workspaces: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Token estimation (always best-effort)
    ai_tokens_in: Optional[int] = None
    ai_tokens_out: Optional[int] = None
    ai_model_ctx_window: Optional[int] = None

    # Best-effort real usage and finish reason (populated if available)
    ai_finish_reason: Optional[str] = None
    ai_usage_prompt: Optional[int] = None
    ai_usage_completion: Optional[int] = None
    ai_usage_total: Optional[int] = None

    def add_paths(self, paths: Iterable[Path], *, source: str) -> None:
        count = 0
        total_bytes = 0
        for p in paths:
            count += 1
            try:
                total_bytes += p.stat().st_size
            except Exception:
                pass
        self.files_total += count
        self.files_by_source[source] = self.files_by_source.get(source, 0) + count
        self.bytes_total += total_bytes
        self.bytes_by_source[source] = self.bytes_by_source.get(source, 0) + total_bytes

    def add_time(self, stage: str, seconds: float) -> None:
        self.time_by_stage[stage] = self.time_by_stage.get(stage, 0.0) + seconds

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def mark_context(self, *, root: Path, workspace: Path) -> None:
        self.contexts += 1
        self.roots.append(str(root))
        self.workspaces.append(str(workspace))

    def finish(self) -> None:
        self.finished_at = time.perf_counter()
        self.duration_s = (
            self.finished_at - self.started_at if self.finished_at else None
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            {
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration_s": self.duration_s,
                "contexts": self.contexts,
                "files_total": self.files_total,
                "files_by_source": self.files_by_source,
                "bytes_total": self.bytes_total,
                "bytes_by_source": self.bytes_by_source,
                "time_by_stage": self.time_by_stage,
                "roots": self.roots,
                "workspaces": self.workspaces,
                "errors": self.errors,
                "ai_tokens_in": self.ai_tokens_in,
                "ai_tokens_out": self.ai_tokens_out,
                "ai_model_ctx_window": self.ai_model_ctx_window,
                "ai_finish_reason": self.ai_finish_reason,
                "ai_usage_prompt": self.ai_usage_prompt,
                "ai_usage_completion": self.ai_usage_completion,
                "ai_usage_total": self.ai_usage_total,
            },
            indent=indent,
        )


class StageTimer:
    def __init__(self, report: ExecutionReport, stage: str):
        self._report = report
        self._stage = stage
        self._t0: float | None = None

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._t0 is not None:
            self._report.add_time(self._stage, time.perf_counter() - self._t0)
        return False