"""
template_engine – Concrete TemplateEngineProtocol implementation for ghconcat.

This module provides a minimal, dependency-free single-brace template engine
that mirrors ghconcat's legacy interpolation semantics while exposing a clean
Protocol-based surface suitable for DI and unit testing.
"""

import logging
from typing import Mapping, Optional

from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.processing.string_interpolator import StringInterpolator


class SingleBraceTemplateEngine(TemplateEngineProtocol):
    """Single-brace template engine using :class:`StringInterpolator`.

    Behaviour is intentionally 1:1 with ghconcat's established rules:
      • {name}      → mapping.get("name", "")
      • {{literal}} → rendered as "{literal}" (escape)
    """

    def __init__(
        self,
        *,
        interpolator: Optional[StringInterpolator] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._interp = interpolator or StringInterpolator()
        self._log = logger or logging.getLogger("ghconcat.templates")

    def render(self, template: str, variables: Mapping[str, str]) -> str:  # type: ignore[override]
        """Render *template* replacing {placeholders} via *variables*."""
        try:
            # Cast to dict to avoid accidental Mapping mutation downstream.
            return self._interp.interpolate(template, dict(variables))
        except Exception as exc:  # noqa: BLE001
            # Defensive: templating must never crash the pipeline.
            self._log.error("template rendering failed: %s", exc)
            return template