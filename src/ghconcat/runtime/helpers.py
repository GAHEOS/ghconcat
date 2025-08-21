from __future__ import annotations
"""
Cohesive helper classes for environment expansion, regex replacements,
and argparse namespace merging.

This module intentionally exposes *only classes*. Legacy free functions
(_apply_replacements, _expand_tokens, _post_parse, _merge_ns, _parse_env_items)
have been removed in favor of instance methods to improve cohesion, testability,
and dependency injection.

Public classes:
- TextReplacer: Regex replace with preserve support.
- EnvExpander: $VAR expansion, --env / --global-env parsing, "none" stripping.
- NamespaceMerger: argparse.Namespace merge logic and post-parse normalization.
"""
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

logger = get_logger('helpers')


class TextReplacer:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._log = logger or get_logger('helpers.replacer')
        self._xf = TextTransformer(logger=self._log, regex_delim='/')

    def apply(self, text: str, replace_specs: Sequence[str] | None, preserve_specs: Sequence[str] | None) -> str:
        """Apply regex replacements with optional preserve regions."""
        return self._xf.apply_replacements(text, replace_specs, preserve_specs)


class EnvExpander:
    def __init__(self, *, logger: logging.Logger | None = None, none_token: str = 'none') -> None:
        self._log = logger or get_logger('helpers.env')
        self._ctx = EnvContext(logger=self._log)
        self._none = none_token

    def parse_items(self, items: Optional[List[str]]) -> Dict[str, str]:
        """Parse --env/-E items into a dict."""
        return self._ctx.parse_items(items)

    def expand_tokens(self, tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
        """Expand $VARS in tokens and strip value==none for value-taking flags."""
        return self._ctx.expand_tokens(tokens, inherited_env, value_flags=_VALUE_FLAGS, none_value=self._none)


class NamespaceMerger:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._log = logger or get_logger('helpers.merge')

    @staticmethod
    def post_parse(ns: argparse.Namespace) -> None:
        """Normalize flags after argparse to match legacy behavior."""
        flags = set(ns.blank_flags or [])
        ns.keep_blank = 'keep' in flags or 'strip' not in flags

        first = set(ns.first_flags or [])
        if 'drop' in first:
            ns.keep_header = False
        else:
            ns.keep_header = 'keep' in first

        hdr = set(ns.hdr_flags or [])
        ns.skip_headers = not ('show' in hdr and 'hide' not in hdr)

        pathf = set(ns.path_flags or [])
        ns.absolute_path = 'absolute' in pathf and 'relative' not in pathf

        if getattr(ns, 'unwrap', False):
            ns.wrap_lang = None
        if getattr(ns, 'no_list', False):
            ns.list_only = False

    def merge(self, parent: argparse.Namespace, child: argparse.Namespace) -> argparse.Namespace:
        """Merge a child namespace into its parent honoring inheritance rules."""
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
                merged[key] = val if val not in (None, '') else merged.get(key)
            else:
                merged[key] = val

        ns = argparse.Namespace(**merged)
        self.post_parse(ns)
        return ns