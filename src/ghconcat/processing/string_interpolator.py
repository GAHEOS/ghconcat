"""
string_interpolator – Minimal {single-brace} template interpolation.

This module encapsulates ghconcat's interpolation semantics into a small,
reusable class:

  • {name}      → replaced by mapping.get("name", "")
  • {{literal}} → rendered as "{literal}" (escape, no interpolation)
  • Mixed/nested sequences preserve the legacy behavior, e.g. "{{{user}}}" →
    "{Leo}" when mapping["user"] == "Leo"

The implementation is streaming and does not rely on heavy templating engines.
"""

import re
from typing import Dict


class StringInterpolator:
    """Single-brace interpolator with double-brace escaping.

    The algorithm is intentionally simple and closely mirrors the original
    monolithic implementation to keep test compatibility 1:1.
    """

    _IDENT_RX = re.compile(r"[A-Za-z_]\w*")

    def interpolate(self, tpl: str, mapping: Dict[str, str]) -> str:
        """Interpolate *tpl* using *mapping* with ghconcat's rules.

        Parameters
        ----------
        tpl:
            Template string potentially containing {placeholders} or {{escapes}}.
        mapping:
            Variable values to inject. Missing keys resolve to "".

        Returns
        -------
        str
            The interpolated result.
        """
        out: list[str] = []
        i = 0
        n = len(tpl)

        def _is_ident(s: str) -> bool:
            return bool(self._IDENT_RX.fullmatch(s))

        while i < n:
            # Escaped braces "{{" → "{", "}}" → "}"
            if tpl.startswith("{{", i):
                out.append("{")
                i += 2
                continue
            if tpl.startswith("}}", i):
                out.append("}")
                i += 2
                continue

            if tpl[i] == "{":
                j = tpl.find("}", i + 1)
                if j != -1:
                    var = tpl[i + 1:j]
                    if _is_ident(var):
                        out.append(mapping.get(var, ""))
                        i = j + 1
                        continue
            out.append(tpl[i])
            i += 1

        return "".join(out)