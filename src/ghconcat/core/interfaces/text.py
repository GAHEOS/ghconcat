from __future__ import annotations
"""Text transformer protocol definitions."""

import re
from typing import Optional, Protocol, Sequence, Tuple


class TextTransformerProtocol(Protocol):
    """Protocol for text transformation helpers.

    Implementations are expected to:
      * Parse a replacement spec into a compiled regex rule.
      * Apply a sequence of replace/preserve rules to a given text.

    Methods:
        parse_replace_spec: Parse a textual spec into (regex, replacement, global_flag).
        apply_replacements: Apply a list of replace and preserve specs to `text`.
    """

    def parse_replace_spec(self, spec: str) -> Optional[Tuple[re.Pattern[str], str, bool]]:
        ...

    def apply_replacements(
        self,
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
    ) -> str:
        ...