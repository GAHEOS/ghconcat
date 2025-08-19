"""
comment_rules – Centralized comment/import/export regex rules for ghconcat.

This module exposes COMMENT_RULES as the single source of truth for:
  • Simple comments (inline) detection
  • Full-line comments removal
  • Import-like statements stripping
  • Export-like statements stripping

It mirrors the legacy mapping previously embedded in ghconcat.py to enable:
  • Zero duplication across modules (ghconcat, line_ops, etc.)
  • Focused unit tests per language/suffix
"""

import re
from typing import Dict, Optional, Tuple, Pattern


COMMENT_RULES: Dict[str, Tuple[
    Pattern[str],            # simple comment
    Pattern[str],            # full-line comment
    Optional[Pattern[str]],  # import-like
    Optional[Pattern[str]],  # export-like
]] = {
    ".py": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*(?:import\b|from\b.+?\bimport\b)"),
        None,
    ),
    ".rb": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*require\b"),
        None,
    ),
    ".php": (
        re.compile(r"^\s*(?://|#)(?!/).*$"),
        re.compile(r"^\s*(?://|#).*$"),
        re.compile(r"^\s*(?:require|include|use)\b"),
        None,
    ),
    ".js": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*(?:export\b|module\.exports\b)"),
    ),
    ".jsx": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".ts": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".tsx": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".dart": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".sh": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*(?:source|\. )"),
        None,
    ),
    ".bash": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*(?:source|\. )"),
        None,
    ),
    ".ps1": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*Import-Module\b"),
        None,
    ),

    ".c": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".cpp": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".cc": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".cxx": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".h": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".hpp": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*#\s*include\b"),
        None,
    ),
    ".go": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),
    ".rs": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*use\b"),
        None,
    ),
    ".java": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),
    ".cs": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*using\b"),
        None,
    ),
    ".swift": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),
    ".kt": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),
    ".kts": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),
    ".scala": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        None,
    ),

    ".yml": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        None,
        None,
    ),
    ".yaml": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        None,
        None,
    ),
    ".sql": (
        re.compile(r"^\s*--(?!-).*$"),
        re.compile(r"^\s*--.*$"),
        None,
        None,
    ),
    ".html": (
        re.compile(r"^\s*<!--(?!-).*-->.*$"),
        re.compile(r"^\s*<!--.*-->.*$"),
        None,
        None,
    ),
    ".xml": (
        re.compile(r"^\s*<!--(?!-).*-->.*$"),
        re.compile(r"^\s*<!--.*-->.*$"),
        None,
        None,
    ),
    ".css": (
        re.compile(r"^\s*/\*(?!\*).*\*/\s*$"),
        re.compile(r"^\s*/\*.*\*/\s*$"),
        None,
        None,
    ),
    ".scss": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        None,
        None,
    ),

    ".r": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*library\("),
        None,
    ),
    ".lua": (
        re.compile(r"^\s*--(?!-).*$"),
        re.compile(r"^\s*--.*$"),
        re.compile(r"^\s*require\b"),
        None,
    ),
    ".pl": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*use\b"),
        None,
    ),
    ".pm": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*use\b"),
        None,
    ),
}