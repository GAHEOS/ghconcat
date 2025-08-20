from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AIProcessorProtocol(Protocol):
    """Thin adapter over OpenAI-like APIs to run a single prompt-to-file job."""

    def run(
        self,
        *,
        prompt: str,
        out_path: Path,
        model: str,
        system_prompt: str,
        temperature: Optional[float],
        top_p: Optional[float],
        presence_penalty: Optional[float],
        frequency_penalty: Optional[float],
        seeds_path: Optional[Path],
        max_tokens: Optional[int],
        reasoning_effort: Optional[str],
    ) -> None:
        """Run the AI job and write the response to `out_path`."""
        ...