from __future__ import annotations

"""
AI processing adapter.

This module keeps a very small, test-friendly adapter that forwards calls
to the CLI-level `_call_openai` function. We keep the argument mapping
exactly as-is to preserve test behavior.
"""
import logging
from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.logging.helpers import get_logger


class AIProcessor(AIProcessorProtocol):
    def __init__(self, *, call_openai, logger: Optional[logging.Logger] = None) -> None:
        self._call = call_openai
        self._log = logger or get_logger('ai.proc')

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
        self._call(
            prompt,
            out_path,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            presence_pen=presence_penalty,
            freq_pen=frequency_penalty,
            seeds_path=seeds_path,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )


class DefaultAIProcessor(AIProcessor):
    pass
