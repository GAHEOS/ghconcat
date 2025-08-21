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


class AIProcessor(AIProcessorProtocol):
    """Thin adapter that delegates to a callable following `_call_openai` shape."""

    def __init__(self, *, call_openai, logger: Optional[logging.Logger] = None) -> None:
        """Initialize the adapter.

        Args:
            call_openai: Callable compatible with the CLI `_call_openai`.
            logger: Optional logger for diagnostics.
        """
        self._call = call_openai
        self._log = logger or logging.getLogger("ghconcat.ai.proc")

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
        """Run the AI call and store the result to `out_path`.

        Notes:
            The CLI layer expects the short parameter names `presence_pen` and
            `freq_pen`. We intentionally forward with those exact names to keep
            compatibility with tests that patch and assert kwargs.

        Args:
            prompt: Input text to process with the model.
            out_path: Destination file path for the AI output.
            model: Model name.
            system_prompt: System prompt to prepend.
            temperature: Sampling temperature (chat models only).
            top_p: Nucleus sampling parameter (chat models only).
            presence_penalty: Presence penalty (chat models only).
            frequency_penalty: Frequency penalty (chat models only).
            seeds_path: Optional JSONL seeds file.
            max_tokens: Maximum output tokens.
            reasoning_effort: Reasoning effort for o-series / gpt-5.
        """
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
    """Default concrete processor. No extra behavior added."""
    pass