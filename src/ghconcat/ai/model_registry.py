from __future__ import annotations
"""Model registry for AI model capabilities and metadata.

This module centralizes the definition of `ModelSpec` along with an extensible
registry that describes model characteristics (reasoning support, endpoint
family, context window, etc.). Keeping this in a dedicated module avoids
duplication and allows multi‑provider support.

Public API:
    - ModelSpec: Dataclass that describes a model family.
    - register_model(alias, spec): Register or override a model spec at runtime.
    - resolve_model_spec(model): Resolve the closest ModelSpec for a given name.
    - context_window_for(model): Convenience to get the context window.
    - default_max_tokens_for(model): Convenience to get default output tokens.
    - get_registry(): Return a copy of the current registry.

Design goals:
    * Single source of truth for model characteristics.
    * Backward compatible with previous behavior (prefix-based resolution).
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelSpec:
    """Immutable description of a model family."""
    family: str
    reasoning: bool
    endpoint: str  # 'chat' | 'responses' | vendor-specific
    supports_temperature: bool
    supports_top_p: bool
    supports_penalties: bool
    supports_logit_bias: bool
    context_window: Optional[int]
    default_max_output_tokens: int


_CTX_4O = 128000
_CTX_5_CHAT = 128000
_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

# Internal canonical registry (lower-cased keys).
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


def register_model(alias: str, spec: ModelSpec) -> None:
    """Register or override a model spec.

    Args:
        alias: Public alias for the model (case-insensitive).
        spec: ModelSpec instance describing capabilities.

    Raises:
        ValueError: If alias is empty.

    Notes:
        - Re-registering an existing alias overrides the previous entry.
        - Aliases are normalized to lower-case for lookups.
        - This hook enables third-party vendors (Anthropic, Google, etc.) to
          expose their models via the same high-level API.
    """
    key = (alias or "").strip().lower()
    if not key:
        raise ValueError("alias must be non-empty")
    _MODEL_SPEC_REGISTRY[key] = spec


def resolve_model_spec(model: str) -> ModelSpec:
    m = (model or "").lower().strip()
    if m.startswith("gpt-5-chat"):
        return _MODEL_SPEC_REGISTRY["gpt-5-chat"]
    if m.startswith("gpt-5"):
        return _MODEL_SPEC_REGISTRY["gpt-5"]
    if m.startswith("gpt-4o"):
        return _MODEL_SPEC_REGISTRY["gpt-4o"]
    if m.startswith(_REASONING_PREFIXES):
        return _MODEL_SPEC_REGISTRY["o-series"]
    return _MODEL_SPEC_REGISTRY["generic-chat"]


def context_window_for(model: str) -> Optional[int]:
    return resolve_model_spec(model).context_window


def default_max_tokens_for(model: str) -> int:
    return resolve_model_spec(model).default_max_output_tokens


def get_registry() -> Dict[str, ModelSpec]:
    """Return a copy of the current model registry."""
    return dict(_MODEL_SPEC_REGISTRY)