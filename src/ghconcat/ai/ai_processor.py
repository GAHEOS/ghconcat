"""
AI processor component for ghconcat.

This module provides:
  • AIProcessorProtocol – now defined in ghconcat.core.interfaces.ai.
  • AIProcessor         – thin wrapper around an injected OpenAI bridge.
  • DefaultAIProcessor  – explicit default implementation.

The bridge callable matches the legacy `_call_openai(...)` signature so
current tests and behavior remain unchanged.
"""

import logging
from pathlib import Path
from typing import Optional

from ghconcat.core.interfaces.ai import AIProcessorProtocol


class AIProcessor(AIProcessorProtocol):
    """Thin wrapper to call the injected OpenAI bridge."""

    def __init__(
        self,
        *,
        call_openai,
        logger: Optional[logging.Logger] = None,
    ) -> None:
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
        """Invoke the OpenAI bridge with the provided parameters."""
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
    """Default implementation; explicit subclass for DI clarity."""
    pass