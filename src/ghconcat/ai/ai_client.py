# -*- coding: utf-8 -*-
"""
ai_client – Robust, production-grade OpenAI integration for ghconcat.

This module provides a self-contained, dependency-injected class to talk to
OpenAI's APIs with strong model-family validation and token pre-validation.

Design highlights
-----------------
• Single entrypoint class: OpenAIClient
• Model-spec registry with capability flags:
    - Reasoning (o‑series, gpt‑5 base) → Responses API + max_output_tokens
      (sampling/penalties are ignored; not supported by these models).
    - Chat (gpt‑4o*, gpt‑5‑chat*) → Chat Completions API
      (supports temperature/top_p/penalties; uses max_tokens).
• Token estimator:
    - Uses `tiktoken` when present; else a safe heuristic (~4 chars/token).
    - Pre-validates prompt + requested max tokens against known context windows
      (e.g., 128k for GPT‑4o and GPT‑5 Chat).
• Backwards compatibility:
    - The outer ghconcat wrapper `_call_openai(...)` is preserved and delegates
      here. Environment toggles are honored there to match current tests.

This class does not perform any CLI env parsing; it focuses on robust API
calls with best-effort defaults.
"""
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

try:  # Optional; ghconcat's tests may run without the SDK installed.
    import openai  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore


@dataclass(frozen=True)
class ModelSpec:
    """Static capabilities and limits for a given model family.

    Attributes
    ----------
    family:
        Human-friendly family name (e.g., 'o-series', 'gpt-4o', 'gpt-5-chat').
    reasoning:
        True for reasoning models (o‑series, gpt‑5 base), False for chat models.
    endpoint:
        'responses' for reasoning, 'chat' for chat.completions.
    supports_temperature:
        Whether `temperature` is accepted.
    supports_top_p:
        Whether `top_p` is accepted.
    supports_penalties:
        Whether presence/frequency penalties are accepted.
    supports_logit_bias:
        Whether `logit_bias` is accepted (not used by ghconcat, here for completeness).
    context_window:
        Max total tokens (input + output). None if unknown/unstable.
    default_max_output_tokens:
        Sensible default when caller does not provide an explicit limit.
    """

    family: str
    reasoning: bool
    endpoint: str  # 'responses' | 'chat'
    supports_temperature: bool
    supports_top_p: bool
    supports_penalties: bool
    supports_logit_bias: bool
    context_window: Optional[int]
    default_max_output_tokens: int


class OpenAIClient:
    """High-level client for OpenAI with model-aware validation.

    Parameters
    ----------
    logger:
        Optional logger for consistent logs. Defaults to 'ghconcat.ai'.
    api_key:
        Explicit API key. If not provided, `OPENAI_API_KEY` is used.
    base_url:
        Override API base URL (rare). When None, the SDK default is used.
    organization:
        Optional organization ID to pass to the client.
    project:
        Optional project ID to pass to the client.
    """

    _REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")  # gpt-5 base (non-chat) ⇒ reasoning
    _CHAT_PREFIXES = ("gpt-4o", "gpt-5-chat")

    # Known context windows (best official public refs as of 2025-08).
    # 4o: 128k (OpenAI docs). 5-chat: 128k (OpenAI model page).
    _CTX_4O = 128_000
    _CTX_5_CHAT = 128_000

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

        if openai is None:
            # Defer hard failure to call time to preserve import-time behavior.
            self._client = None
        else:
            # The modern SDK exposes OpenAI() as the root client.
            self._client = openai.OpenAI(  # type: ignore[attr-defined]
                api_key=self._api_key or None,
                base_url=self._base_url,
                organization=self._organization,
                project=self._project,
            )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

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
        """Generate a completion using the appropriate OpenAI endpoint.

        This method:
          1) Builds `messages` from system/seeds/user.
          2) Resolves the model spec and filters unsupported params.
          3) Estimates tokens and clamps `max_*tokens` to context window.
          4) Calls either Chat Completions or Responses API.
          5) Returns the plain text output.

        Parameters
        ----------
        prompt:
            The user message body to send last in the chat.
        model:
            The OpenAI model identifier (e.g., 'gpt-4o', 'o3', 'gpt-5-chat-latest').
        system_prompt:
            Optional system/developer preface message.
        temperature/top_p/presence_penalty/frequency_penalty:
            Sampling knobs (ignored for reasoning models).
        seeds_path:
            Optional JSONL file with seed chat messages (role/content).
        timeout:
            Network timeout in seconds.
        max_tokens:
            Desired max output tokens. If None, a default per-model is used.
            For reasoning/Responses, this maps to `max_output_tokens`. For chat,
            it maps to `max_tokens`.
        reasoning_effort:
            Optional override for reasoning models ('low'|'medium'|'high').
            If not provided, falls back to GHCONCAT_AI_REASONING_EFFORT or 'medium'.

        Returns
        -------
        str
            The model's final text output (empty string on failure).
        """
        if self._client is None or not self._api_key:
            self._log.warning("OpenAI SDK/API key not available.")
            return "⚠ OpenAI disabled"

        spec = self._resolve_model_spec(model)
        messages = self._build_messages(system_prompt, seeds_path, prompt)

        # Compute safe token budgets.
        desired_max = self._resolve_max_tokens(spec, max_tokens)
        safe_max = self._prevalidate_and_clamp_tokens(spec, model, messages, desired_max)

        try:
            if spec.endpoint == "responses":
                # Reasoning models: use Responses API + max_output_tokens.
                eff = (reasoning_effort or
                       os.getenv("GHCONCAT_AI_REASONING_EFFORT") or "medium")
                eff = eff.lower().strip()
                if eff not in {"low", "medium", "high"}:
                    eff = "medium"

                payload: Dict[str, Any] = {
                    "model": model,
                    "input": messages,
                    "max_output_tokens": safe_max,
                    "timeout": timeout,
                    "reasoning": {"effort": eff},
                }
                rsp = self._client.responses.create(**payload)  # type: ignore[call-arg]
                return self._extract_text(rsp) or ""

            # Chat models: Chat Completions + sampling knobs.
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

            rsp = self._client.chat.completions.create(**payload)  # type: ignore[call-arg]
            return self._extract_text(rsp) or ""
        except Exception as exc:  # noqa: BLE001
            self._log.error("OpenAI error: %s", exc)
            return f"⚠ OpenAI error: {exc}"

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _resolve_model_spec(self, model: str) -> ModelSpec:
        """Return a ModelSpec with capabilities for *model*."""
        m = (model or "").lower().strip()

        # 1) gpt‑5 chat (chat model, sampling allowed)
        if m.startswith("gpt-5-chat"):
            return ModelSpec(
                family="gpt-5-chat",
                reasoning=False,
                endpoint="chat",
                supports_temperature=True,
                supports_top_p=True,
                supports_penalties=True,
                supports_logit_bias=True,
                context_window=self._CTX_5_CHAT,
                default_max_output_tokens=4096,
            )

        # 2) gpt‑5 base (reasoning)
        if m.startswith("gpt-5"):
            return ModelSpec(
                family="gpt-5",
                reasoning=True,
                endpoint="responses",
                supports_temperature=False,
                supports_top_p=False,
                supports_penalties=False,
                supports_logit_bias=False,
                context_window=None,  # may vary by deployment; skip hard cap
                default_max_output_tokens=4096,
            )

        # 3) GPT‑4o family (chat, sampling allowed)
        if m.startswith("gpt-4o"):
            # Some preview/search variants may impose special restrictions,
            # but we keep the general chat capability set here.
            return ModelSpec(
                family="gpt-4o",
                reasoning=False,
                endpoint="chat",
                supports_temperature=True,
                supports_top_p=True,
                supports_penalties=True,
                supports_logit_bias=True,
                context_window=self._CTX_4O,
                default_max_output_tokens=4096,
            )

        # 4) o‑series (reasoning): o1*, o3*, o4* → no sampling knobs
        if m.startswith(self._REASONING_PREFIXES):
            return ModelSpec(
                family="o-series",
                reasoning=True,
                endpoint="responses",
                supports_temperature=False,
                supports_top_p=False,
                supports_penalties=False,
                supports_logit_bias=False,
                context_window=None,
                default_max_output_tokens=4096,
            )

        # 5) Fallback as chat-capable model (conservative default)
        return ModelSpec(
            family="generic-chat",
            reasoning=False,
            endpoint="chat",
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=None,
            default_max_output_tokens=1024,
        )

    def _build_messages(
        self,
        system_prompt: str,
        seeds_path: Optional[Path],
        user_prompt: str,
    ) -> List[Dict[str, str]]:
        """Construct OpenAI-style `messages` from system/seeds/user."""
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if seeds_path and seeds_path.exists():
            for line in seeds_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and {"role", "content"} <= set(obj.keys()):
                        role = str(obj["role"])
                        content = str(obj["content"])
                        messages.append({"role": role, "content": content})
                    else:
                        messages.append({"role": "user", "content": line.strip()})
                except json.JSONDecodeError:
                    messages.append({"role": "user", "content": line.strip()})

        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _resolve_max_tokens(self, spec: ModelSpec, explicit: Optional[int]) -> int:
        """Return a sane max tokens value for the model."""
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
        """Clamp max tokens to fit within the context window when known."""
        if not spec.context_window:  # unknown window → skip
            return desired_max

        used = self._estimate_tokens(messages, model)
        # Ensure room for the output. If negative, keep a small minimum.
        available_for_output = max(1, spec.context_window - used)
        if desired_max > available_for_output:
            self._log.warning(
                "max tokens reduced: requested=%d, available=%d (model=%s, ctx=%s)",
                desired_max, available_for_output, model, spec.context_window,
            )
            return available_for_output
        return desired_max

    def _estimate_tokens(
        self,
        messages: Iterable[Dict[str, str]],
        model: str,
    ) -> int:
        """Return a best-effort token estimate for *messages*."""
        text = "\n".join(str(m.get("role", "")) + ": " + str(m.get("content", "")) for m in messages)
        # 1) Try tiktoken (if available).
        try:  # pragma: no cover (optional dependency)
            import tiktoken  # type: ignore
            try:
                enc = tiktoken.encoding_for_model(model)
            except Exception:
                # Fall back to a widely supported encoding.
                enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass

        # 2) Fallback heuristic: ~4 chars/token (safe upper-boundish).
        # Avoid zero for very short strings.
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _extract_text(api_result: Any) -> str:
        """Extract plain text from Responses or Chat Completions result."""
        # Newer SDKs (responses) expose `output_text`.
        txt = getattr(api_result, "output_text", None)
        if isinstance(txt, str) and txt.strip():
            return txt

        # Chat Completions
        try:
            choices = getattr(api_result, "choices", None)
            if choices and choices[0].message and choices[0].message.content:
                return str(choices[0].message.content)
        except Exception:
            pass

        # Responses raw structure (fallback): iterate output content.
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

        # Last resort: string coercion.
        return str(api_result or "").strip()