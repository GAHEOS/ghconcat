from typing import Mapping, Protocol

class TemplateEngineProtocol(Protocol):
    """Single-brace templating compatible with current CLI semantics."""
    def render(self, template: str, variables: Mapping[str, str]) -> str: ...