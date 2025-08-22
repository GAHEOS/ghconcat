from __future__ import annotations

import os
import ssl

import argparse
import logging
from copy import deepcopy
from typing import Dict, List, Optional, Sequence

from ghconcat.parsing.attr_sets import (
    _BOOL_ATTRS,
    _FLT_ATTRS,
    _INT_ATTRS,
    _LIST_ATTRS,
    _NON_INHERITED,
    _STR_ATTRS,
    _VALUE_FLAGS,
)
from ghconcat.processing.envctx import EnvContext
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.logging.helpers import get_logger

logger = get_logger("helpers")


class TextReplacer:
    """Regex-based replacer with preserve support."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._log = logger or get_logger("helpers.replacer")
        self._xf = TextTransformer(logger=self._log, regex_delim="/")

    def apply(
            self,
            text: str,
            replace_specs: Sequence[str] | None,
            preserve_specs: Sequence[str] | None,
    ) -> str:
        """Apply replacements with optional preserve rules."""
        return self._xf.apply_replacements(text, replace_specs, preserve_specs)


class EnvExpander:
    """Environment token expander for CLI tokens."""

    def __init__(
            self, *, logger: logging.Logger | None = None, none_token: str = "none"
    ) -> None:
        self._log = logger or get_logger("helpers.env")
        self._ctx = EnvContext(logger=self._log)
        self._none = none_token

    def parse_items(self, items: Optional[List[str]]) -> Dict[str, str]:
        """Parse VAR=VAL items as a mapping."""
        return self._ctx.parse_items(items)

    def expand_tokens(self, tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
        """Expand $VARS in tokens and drop flags whose value is 'none'."""
        return self._ctx.expand_tokens(
            tokens, inherited_env, value_flags=_VALUE_FLAGS, none_value=self._none
        )


class NamespaceMerger:
    """argparse.Namespace merge utilities with post-parse normalization."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._log = logger or get_logger("helpers.merge")

    @staticmethod
    def post_parse(ns: argparse.Namespace) -> None:
        """Normalize mutually exclusive/derived flags in-place."""
        flags = set(ns.blank_flags or [])
        ns.keep_blank = "keep" in flags or "strip" not in flags

        first = set(ns.first_flags or [])
        if "drop" in first:
            ns.keep_header = False
        else:
            ns.keep_header = "keep" in first

        hdr = set(ns.hdr_flags or [])
        ns.skip_headers = not ("show" in hdr and "hide" not in hdr)

        pathf = set(ns.path_flags or [])
        ns.absolute_path = "absolute" in pathf and "relative" not in pathf

        if getattr(ns, "unwrap", False):
            ns.wrap_lang = None
        if getattr(ns, "no_list", False):
            ns.list_only = False

    def merge(self, parent: argparse.Namespace, child: argparse.Namespace) -> argparse.Namespace:
        """Merge two namespaces following inheritance rules."""
        merged = deepcopy(vars(parent))
        for key, val in vars(child).items():
            if key in _NON_INHERITED:
                merged[key] = val
                continue
            if key in _LIST_ATTRS:
                merged[key] = [*(merged.get(key) or []), *(val or [])]
            elif key in _BOOL_ATTRS:
                merged[key] = val or merged.get(key, False)
            elif key in _INT_ATTRS | _FLT_ATTRS:
                merged[key] = val if val is not None else merged.get(key)
            elif key in _STR_ATTRS:
                merged[key] = val if val not in (None, "") else merged.get(key)
            else:
                merged[key] = val
        ns = argparse.Namespace(**merged)
        self.post_parse(ns)
        return ns


# ------------------------------
# Lazy helpers (new)
# ------------------------------

def make_line_ops(logger: logging.Logger | None = None):
    """Build a LineProcessingService with lazy COMMENT_RULES fallback.

    This function defers heavy imports to keep top-level modules clean.
    If COMMENT_RULES cannot be imported, an empty rule-set is used, which
    safely disables regex-based comment/import/export stripping while
    preserving other functionality.

    Args:
        logger: Optional logger for the service.

    Returns:
        An instance exposing `.slice_lines` and `.clean_lines`.
    """
    import re as _re  # local import to avoid polluting top-level modules

    try:
        # Fallback-friendly import: if it fails, we degrade gracefully.
        from ghconcat.processing.comment_rules import COMMENT_RULES as _CR  # type: ignore
    except Exception:
        _CR = {}

    # Imported lazily to avoid top-level dependency in callers.
    from ghconcat.processing.line_ops import LineProcessingService as _LPS  # type: ignore

    rx = _re.compile(r"^\s*#\s*line\s*1\d*\s*$")
    return _LPS(comment_rules=_CR, line1_re=rx, logger=logger or get_logger("helpers.lineops"))


def get_ssl_ctx_provider(url: str) -> Optional[ssl.SSLContext]:
    """Return the canonical `ssl_context_for` provider or a no-op fallback.

    The returned callable has the signature: (url: str) -> ssl.SSLContext | None

    This lazy indirection allows callers to remove the explicit import from
    top-level modules while preserving behavior and tests.

    Returns:
        A callable to provide an SSL context per URL, or a no-op returning None.
    """
    if not url.lower().startswith('https://'):
        return None
    if os.getenv('GHCONCAT_INSECURE_TLS') == '1':
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None
