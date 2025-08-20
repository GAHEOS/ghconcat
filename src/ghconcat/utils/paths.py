# src/ghconcat/utils/paths.py
"""
paths – Small, centralized path and source-type helpers for ghconcat.

Provides:
  • is_hidden_path(Path)         – dot-segment detection
  • is_within_dir(path, parent)  – containment check
  • looks_like_url(str)          – quick http(s) URL check
  • looks_like_git_spec(str)     – robust Git-spec heuristic
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def is_hidden_path(p: Path) -> bool:
    """Return True if *p* has any hidden segment (leading-dot component)."""
    return any(part.startswith(".") for part in p.parts)


def is_within_dir(path: Path, parent: Path) -> bool:
    """Return True if *path* is contained inside *parent*."""
    try:
        path.resolve().relative_to(Path(parent).resolve())
        return True
    except Exception:
        return False


def looks_like_url(s: str) -> bool:
    """Return True for plain http(s) URLs (scheme-based)."""
    s = (s or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


# Common Git forges and hosts; heuristic is permissive but avoids false positives
_KNOWN_GIT_HOST_TOKENS = (
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "codeberg.org",
    "sr.ht",
    "sourcehut.org",
    "gitea",            # self-hosted patterns often include 'gitea'
    "dev.azure.com",
    "visualstudio.com",
)


def looks_like_git_spec(s: str) -> bool:
    """Return True if *s* likely denotes a Git repository 'spec'.

    Heuristics:
      • 'git@host:org/repo'             → True
      • contains '^' (branch selector)  → True
      • ends with '.git'                → True
      • http(s) URL whose host matches a known forge → True
        (e.g., https://github.com/org/repo[/subpath])

    Notes
    -----
    This heuristic intentionally does **not** treat generic websites or
    raw-content CDNs (e.g., raw.githubusercontent.com) as Git specs; those
    remain plain URLs and are fetched directly.
    """
    s = (s or "").strip()

    if s.startswith("git@"):
        return True
    if "^" in s:
        return True
    if s.endswith(".git"):
        return True
    if looks_like_url(s):
        host = urlparse(s).netloc.lower()
        return any(tok in host for tok in _KNOWN_GIT_HOST_TOKENS)

    return False