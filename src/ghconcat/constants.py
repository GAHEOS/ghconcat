from __future__ import annotations

"""Project-wide constants used across modules.

This module isolates public constants to reduce cross-module coupling.
"""

# Public banner delimiter used in headers. Tests import it as `ghconcat.HEADER_DELIM`.
HEADER_DELIM: str = '===== '