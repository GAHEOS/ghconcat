from __future__ import annotations
"""
Token budget estimator utilities.

Adds public `estimate_text_tokens` for plain text strings, complementing
message-based estimation.
"""

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional


@dataclass(frozen=True)
class TokenEstimation:
    tokens_in: int
    tokens_available_for_output: Optional[int] = None


class TokenBudgetEstimator:
    @staticmethod
    def _safe_len_tokens(text: str, *, model: str) -> int:
        try:
            import tiktoken
            try:
                enc = tiktoken.encoding_for_model(model)
            except Exception:
                enc = tiktoken.get_encoding('cl100k_base')
            return len(enc.encode(text))
        except Exception:
            # Fallback: ~4 chars per token
            return max(1, (len(text) + 3) // 4)

    def estimate_messages_tokens(
        self,
        messages: Iterable[Mapping[str, str]],
        *,
        model: str,
        context_window: Optional[int],
    ) -> TokenEstimation:
        text = '\n'.join((f"{m.get('role', '')}: {m.get('content', '')}" for m in messages))
        used = self._safe_len_tokens(text, model=model)
        available: Optional[int] = None
        if isinstance(context_window, int) and context_window > 0:
            available = max(1, context_window - used)
        return TokenEstimation(tokens_in=used, tokens_available_for_output=available)

    @staticmethod
    def clamp_max_output(desired_max: int, available_for_output: Optional[int]) -> int:
        if available_for_output is None:
            return desired_max
        return max(1, min(desired_max, available_for_output))

    def estimate_text_tokens(self, text: str, *, model: str) -> int:
        """Return a conservative estimate for token count of plain text."""
        return self._safe_len_tokens(text, model=model)