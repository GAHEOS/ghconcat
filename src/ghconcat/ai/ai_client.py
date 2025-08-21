# src/ghconcat/ai/ai_client.py
from __future__ import annotations

"""
OpenAI client wrapper and model metadata.

This module provides a small compatibility layer around the OpenAI SDK, offering:
  * A normalized way to describe models via `ModelSpec`.
  * A single entry point `OpenAIClient.generate_chat_completion(...)`
    that hides the differences between Chat Completions and Responses APIs.
  * Safe fallbacks and defensive error handling.

Behavioral note:
    This refactor adds type hints and docstrings and delegates token estimation
    to TokenBudgetEstimator without changing public behavior.

New in this refactor:
    - `last_usage`: best-effort capture of real usage from the SDK response
      (prompt_tokens, completion_tokens, total_tokens) when available.
    - `last_finish_reason`: best-effort capture of finish reason when available.
    - `_build_messages` now delegates to `ghconcat.ai.message_utils.build_chat_messages`
      to eliminate duplication across the codebase.
"""

import json
import logging
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import openai  # type: ignore
except ModuleNotFoundError:
    openai = None

from ghconcat.ai.token_budget import TokenBudgetEstimator
from ghconcat.ai.message_utils import build_chat_messages


@dataclass(frozen=True)
class ModelSpec:
    """Describes API capabilities and defaults for a model family."""
    family: str
    reasoning: bool
    endpoint: str
    supports_temperature: bool
    supports_top_p: bool
    supports_penalties: bool
    supports_logit_bias: bool
    context_window: Optional[int]
    default_max_output_tokens: int


class OpenAIClient:
    """A minimal adapter over the OpenAI SDK with robust fallbacks.

    The adapter abstracts Chat Completions vs Responses APIs and provides
    token budgeting assistance and response metadata tracking.
    """

    _REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")
    _CHAT_PREFIXES = ("gpt-4o", "gpt-5-chat")

    _CTX_4O = 128000
    _CTX_5_CHAT = 128000

    _MODEL_SPEC_REGISTRY: Dict[str, ModelSpec] = {
        "gpt-5-chat": ModelSpec(
            family="gpt-5-chat",
            reasoning=False,
            endpoint="chat",
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=_CTX_5_CHAT,
            default_max_output_tokens=4096,
        ),
        "gpt-5": ModelSpec(
            family="gpt-5",
            reasoning=True,
            endpoint="responses",
            supports_temperature=False,
            supports_top_p=False,
            supports_penalties=False,
            supports_logit_bias=False,
            context_window=None,
            default_max_output_tokens=4096,
        ),
        "gpt-4o": ModelSpec(
            family="gpt-4o",
            reasoning=False,
            endpoint="chat",
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=_CTX_4O,
            default_max_output_tokens=4096,
        ),
        "o-series": ModelSpec(
            family="o-series",
            reasoning=True,
            endpoint="responses",
            supports_temperature=False,
            supports_top_p=False,
            supports_penalties=False,
            supports_logit_bias=False,
            context_window=None,
            default_max_output_tokens=4096,
        ),
        "generic-chat": ModelSpec(
            family="generic-chat",
            reasoning=False,
            endpoint="chat",
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=None,
            default_max_output_tokens=1024,
        ),
    }

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        project: Optional[str] = None,
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.ai")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL") or None
        self._organization = organization or os.getenv("OPENAI_ORG") or None
        self._project = project or os.getenv("OPENAI_PROJECT") or None

        # Lazily initialize SDK client if available; keep tests safe otherwise.
        if openai is None:
            self._client = None
        else:
            self._client = openai.OpenAI(
                api_key=self._api_key or None,
                base_url=self._base_url,
                organization=self._organization,
                project=self._project,
            )

        self._estimator = TokenBudgetEstimator()
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_finish_reason: Optional[str] = None

    def generate_chat_completion(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        seeds_path: Optional[Path] = None,
        timeout: int = 1800,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """Invoke OpenAI API using the appropriate endpoint.

        Returns a best-effort text extraction or a defensive error marker string.
        """
        if self._client is None or not self._api_key:
            self._log.warning("OpenAI SDK/API key not available.")
            return "⚠ OpenAI disabled"

        spec = self._resolve_model_spec(model)
        messages = self._build_messages(system_prompt, seeds_path, prompt)

        desired_max = self._resolve_max_tokens(spec, max_tokens)
        safe_max = self._prevalidate_and_clamp_tokens(spec, model, messages, desired_max)

        self.last_usage = None
        self.last_finish_reason = None

        try:
            if spec.endpoint == "responses":
                eff = (
                    (reasoning_effort or os.getenv("GHCONCAT_AI_REASONING_EFFORT") or "medium")
                    .lower()
                    .strip()
                )
                if eff not in {"low", "medium", "high"}:
                    eff = "medium"
                payload: Dict[str, Any] = {
                    "model": model,
                    "input": messages,
                    "max_output_tokens": safe_max,
                    "timeout": timeout,
                    "reasoning": {"effort": eff},
                }
                rsp = self._client.responses.create(**payload)
                self._record_metrics(rsp)
                return self._extract_text(rsp) or ""

            # Chat Completions
            payload = {
                "model": model,
                "messages": messages,
                "timeout": timeout,
                "max_tokens": safe_max,
            }
            if spec.supports_temperature and temperature is not None:
                payload["temperature"] = temperature
            if spec.supports_top_p and top_p is not None:
                payload["top_p"] = top_p
            if spec.supports_penalties and presence_penalty is not None:
                payload["presence_penalty"] = presence_penalty
            if spec.supports_penalties and frequency_penalty is not None:
                payload["frequency_penalty"] = frequency_penalty

            rsp = self._client.chat.completions.create(**payload)
            self._record_metrics(rsp)
            return self._extract_text(rsp) or ""
        except Exception as exc:
            self._log.error("OpenAI error: %s", exc)
            return f"⚠ OpenAI error: {exc}"

    def _resolve_model_spec(self, model: str) -> ModelSpec:
        """Map model name prefixes to a ModelSpec."""
        m = (model or "").lower().strip()
        if m.startswith("gpt-5-chat"):
            return self._MODEL_SPEC_REGISTRY["gpt-5-chat"]
        if m.startswith("gpt-5"):
            return self._MODEL_SPEC_REGISTRY["gpt-5"]
        if m.startswith("gpt-4o"):
            return self._MODEL_SPEC_REGISTRY["gpt-4o"]
        if m.startswith(self._REASONING_PREFIXES):
            return self._MODEL_SPEC_REGISTRY["o-series"]
        return self._MODEL_SPEC_REGISTRY["generic-chat"]

    def _build_messages(
        self, system_prompt: str, seeds_path: Optional[Path], user_prompt: str
    ) -> List[Dict[str, str]]:
        """Delegate message construction to the shared utility.

        Keeping this method preserves the internal structure and allows
        targeted testing while eliminating code duplication.
        """
        return build_chat_messages(
            system_prompt=system_prompt,
            seeds_path=seeds_path,
            user_prompt=user_prompt,
        )

    def _resolve_max_tokens(self, spec: ModelSpec, explicit: Optional[int]) -> int:
        """Resolve explicit / env / default max tokens."""
        if isinstance(explicit, int) and explicit > 0:
            return explicit
        env_val = os.getenv("GHCONCAT_AI_MAX_TOKENS")
        if env_val:
            try:
                n = int(env_val)
                if n > 0:
                    return n
            except ValueError:
                self._log.warning("Invalid GHCONCAT_AI_MAX_TOKENS=%r; ignoring.", env_val)
        return spec.default_max_output_tokens

    def _prevalidate_and_clamp_tokens(
        self,
        spec: ModelSpec,
        model: str,
        messages: List[Dict[str, str]],
        desired_max: int,
    ) -> int:
        """Clamp `max_tokens` based on estimated available context."""
        if not spec.context_window:
            return desired_max
        est = self._estimator.estimate_messages_tokens(
            messages, model=model, context_window=spec.context_window
        )
        if est.tokens_available_for_output is not None and desired_max > est.tokens_available_for_output:
            self._log.warning(
                "max tokens reduced: requested=%d, available=%d (model=%s, ctx=%s)",
                desired_max,
                est.tokens_available_for_output,
                model,
                spec.context_window,
            )
        return self._estimator.clamp_max_output(desired_max, est.tokens_available_for_output)

    @staticmethod
    def _extract_text(api_result: Any) -> str:
        """Best-effort extraction of text from various OpenAI SDK result shapes."""
        # Responses API convenience
        txt = getattr(api_result, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            return txt

        # Chat Completions API
        try:
            choices = getattr(api_result, "choices", None)
            if choices and choices[0].message and choices[0].message.content:
                return str(choices[0].message.content)
        except Exception:
            pass

        # Responses API "output" array
        try:
            out = getattr(api_result, "output", None)
            if isinstance(out, list):
                chunks: List[str] = []
                for item in out:
                    content = getattr(item, "content", None)
                    if isinstance(content, list):
                        for c in content:
                            val = getattr(c, "text", None)
                            if val:
                                chunks.append(str(val))
                if chunks:
                    return "\n".join(chunks)
        except Exception:
            pass

        # Fallback: stringify the object
        return str(api_result or "").strip()

    def _record_metrics(self, rsp: Any) -> None:
        """Capture best-effort usage and finish_reason fields."""
        try:
            self.last_usage = self._extract_usage(rsp)
        except Exception:
            self.last_usage = None
        try:
            self.last_finish_reason = self._extract_finish_reason(rsp)
        except Exception:
            self.last_finish_reason = None

    @staticmethod
    def _getattr_path(obj: Any, path: str) -> Any:
        """Helper to chain getattr calls safely."""
        cur = obj
        for name in path.split("."):
            cur = getattr(cur, name, None)
            if cur is None:
                return None
        return cur

    def _extract_usage(self, rsp: Any) -> Optional[Dict[str, int]]:
        """Extract usage metrics from diverse SDK result shapes."""
        candidates = [
            self._getattr_path(rsp, "usage"),
            self._getattr_path(rsp, "response"),
            self._getattr_path(rsp, "response.usage"),
            self._getattr_path(rsp, "meta.usage"),
        ]
        usage_obj = None
        for cand in candidates:
            if cand and hasattr(cand, "prompt_tokens"):
                usage_obj = cand
                break
            if isinstance(cand, dict) and "prompt_tokens" in cand:
                usage_obj = cand
                break
            if cand and hasattr(cand, "usage"):
                inner = getattr(cand, "usage", None)
                if inner is not None:
                    usage_obj = inner
                    break

        if usage_obj is None:
            return None

        def _as_int(v: Any) -> Optional[int]:
            try:
                return int(v)
            except Exception:
                return None

        if isinstance(usage_obj, dict):
            return {
                k: v
                for k, v in {
                    "prompt_tokens": _as_int(usage_obj.get("prompt_tokens")),
                    "completion_tokens": _as_int(usage_obj.get("completion_tokens")),
                    "total_tokens": _as_int(usage_obj.get("total_tokens")),
                }.items()
                if v is not None
            }
        return {
            k: v
            for k, v in {
                "prompt_tokens": _as_int(getattr(usage_obj, "prompt_tokens", None)),
                "completion_tokens": _as_int(getattr(usage_obj, "completion_tokens", None)),
                "total_tokens": _as_int(getattr(usage_obj, "total_tokens", None)),
            }.items()
            if v is not None
        }

    def _extract_finish_reason(self, rsp: Any) -> Optional[str]:
        """Extract finish_reason from multiple possible locations."""
        try:
            choices = getattr(rsp, "choices", None)
            if choices:
                first = choices[0]
                val = getattr(first, "finish_reason", None)
                if val:
                    return str(val)
                if isinstance(first, dict) and first.get("finish_reason"):
                    return str(first["finish_reason"])
        except Exception:
            pass
        try:
            resp = self._getattr_path(rsp, "response")
            if resp:
                choices = getattr(resp, "choices", None)
                if choices:
                    first = choices[0]
                    val = getattr(first, "finish_reason", None)
                    if val:
                        return str(val)
                    if isinstance(first, dict) and first.get("finish_reason"):
                        return str(first["finish_reason"])
        except Exception:
            pass
        try:
            val = getattr(rsp, "finish_reason", None)
            if val:
                return str(val)
        except Exception:
            pass
        return None