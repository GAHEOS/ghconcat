from __future__ import annotations
from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class TemplateEngineProtocol(Protocol):
    """Protocol for very small, string-based template engines."""

    def render(self, template: str, variables: Mapping[str, str]) -> str:
        ...