from __future__ import annotations
"""OpenAI client wrapper and model metadata.

This module provides a compatibility layer around the OpenAI SDK, offering:

* A normalized way to describe models via `ModelSpec` (now in ai.model_registry).
* A single entry point `OpenAIClient.generate_chat_completion(...)` that hides
  the differences between Chat Completions and Responses APIs.
* Defensive error handling and best-effort usage/finish reason extraction.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import openai  # type: ignore
except ModuleNotFoundError:
    openai = None

from ghconcat.ai.token_budget import TokenBudgetEstimator
from ghconcat.ai.message_utils import build_chat_messages
from ghconcat.ai.model_registry import ModelSpec, resolve_model_spec
from ghconcat.logging.helpers import get_logger


class OpenAIClient:
    """Thin OpenAI SDK adapter with defensive parsing and metrics caching."""

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        project: Optional[str] = None,
    ) -> None:
        """Initialize the client.

        Args:
            logger: Optional logger instance.
            api_key: Explicit API key, otherwise read from OPENAI_API_KEY.
            base_url: Optional custom endpoint base URL.
            organization: Optional OpenAI organization ID.
            project: Optional OpenAI project ID.
        """
        self._log = logger or get_logger("ai")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL") or None
        self._organization = organization or os.getenv("OPENAI_ORG") or None
        self._project = project or os.getenv("OPENAI_PROJECT") or None

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
        """Generate a completion using either Chat or Responses API.

        The endpoint and supported parameters are derived from the resolved
        `ModelSpec`. Unsupported parameters are silently ignored.

        Returns:
            The text output (empty string on error).
        """
        if self._client is None or not self._api_key:
            self._log.warning("OpenAI SDK/API key not available.")
            return "⚠ OpenAI disabled"

        spec = resolve_model_spec(model)
        messages = build_chat_messages(
            system_prompt=system_prompt, seeds_path=seeds_path, user_prompt=prompt
        )

        desired_max = self._resolve_max_tokens(spec, max_tokens)
        safe_max = self._prevalidate_and_clamp_tokens(spec, model, messages, desired_max)

        self.last_usage = None
        self.last_finish_reason = None

        try:
            if spec.endpoint == "responses":
                eff = (
                    reasoning_effort or os.getenv("GHCONCAT_AI_REASONING_EFFORT") or "medium"
                ).lower().strip()
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

            # Chat Completions API
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

    def _resolve_max_tokens(self, spec: ModelSpec, explicit: Optional[int]) -> int:
        """Determine the max output tokens honoring explicit/env/default."""
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
        """Clamp the requested output tokens to the estimated available window."""
        if not spec.context_window:
            return desired_max
        est = self._estimator.estimate_messages_tokens(
            messages, model=model, context_window=spec.context_window
        )
        if (
            est.tokens_available_for_output is not None
            and desired_max > est.tokens_available_for_output
        ):
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
        """Best-effort extraction of text from OpenAI SDK result."""
        txt = getattr(api_result, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            return txt

        try:
            choices = getattr(api_result, "choices", None)
            if choices and choices[0].message and choices[0].message.content:
                return str(choices[0].message.content)
        except Exception:
            pass

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

        return str(api_result or "").strip()

    def _record_metrics(self, rsp: Any) -> None:
        """Capture usage/finish_reason in a resilient way for sidecar meta."""
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
        cur = obj
        for name in path.split("."):
            cur = getattr(cur, name, None)
            if cur is None:
                return None
        return cur

    def _extract_usage(self, rsp: Any) -> Optional[Dict[str, int]]:
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