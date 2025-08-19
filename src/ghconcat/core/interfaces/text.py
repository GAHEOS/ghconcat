from typing import Optional, Protocol, Sequence, Tuple
import re


class ReplaceSpec:
    """Lightweight marker class kept for compatibility with public imports.

    Implementations may ignore this type and expose their own internal
    representation. It remains here to keep a stable import surface.
    """
    # Intentionally empty; ghconcat's concrete implementation does not
    # depend on this structure at runtime.


class TextTransformerProtocol(Protocol):
    """Apply replacements/preserves and text cleanups (ghconcat semantics)."""

    def parse_replace_spec(
        self,
        spec: str,
    ) -> Optional[Tuple[re.Pattern[str], str, bool]]: ...

    def apply_replacements(
        self,
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
    ) -> str: ...