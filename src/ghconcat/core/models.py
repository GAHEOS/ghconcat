from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, Literal

# Single source of truth for runtime reports
ReasoningEffort = Literal['low', 'medium', 'high']


@dataclass(frozen=True)
class ContextConfig:
    """Lightweight context carrier for programmatic engine runs."""
    name: str
    cwd: Path
    workspace: Path | None = None
    include: Sequence[str] = ()
    exclude: Sequence[str] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    flags: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    header: str | None
    body: str
    delim: str | None = None


@dataclass(frozen=True)
class FileEntry:
    path: Path
    relpath: str
    size: int
    mime: str | None = None


@dataclass(frozen=True)
class ReaderHint:
    suffix: str | None = None
    mime: str | None = None
    sample: bytes | None = None


@dataclass(frozen=True)
class FetchRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None
    timeout: float | None = None


@dataclass(frozen=True)
class FetchResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


@dataclass(frozen=True)
class AIOptions:
    model: str
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    reasoning_effort: ReasoningEffort | None = None


@dataclass(frozen=True)
class AIResult:
    text: str
    tokens_in: int
    tokens_out: int
    finish_reason: str | None = None