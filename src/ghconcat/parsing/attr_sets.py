"""
Centralized CLI attribute sets for ghconcat.

This module consolidates the canonical attribute-category sets used by the
CLI layer to merge argparse namespaces across contexts while preserving the
legacy behavior of the original monolithic implementation.

Notes
-----
• Set contents remain intentionally 1:1 with the previous in-module values
  from `cli.py` to guarantee full test compatibility.
"""
from __future__ import annotations
from typing import Set

_VALUE_FLAGS: Set[str] = {
    "-w", "--workdir",
    "-W", "--workspace",
    "-a", "--add-path",
    "-A", "--exclude-path",
    "--url-depth",
    "-s", "--suffix",
    "-S", "--exclude-suffix",
    "-n", "--total-lines",
    "-N", "--start-line",
    "-t", "--template",
    "-T", "--child-template",
    "-o", "--output",
    "-u", "--wrap",
    "--ai-model",
    "--ai-system-prompt",
    "--ai-seeds",
    "--ai-temperature",
    "--ai-top-p",
    "--ai-presence-penalty",
    "--ai-frequency-penalty",
    "--ai-max-tokens",
    "--ai-reasoning-effort",
    "-e", "--env",
    "-E", "--global-env",
    "-y", "--replace",
    "-Y", "--preserve",
}

_INT_ATTRS: Set[str] = {
    "total_lines",
    "first_line",
    "url_depth",
    "ai_max_tokens",
}

_LIST_ATTRS: Set[str] = {
    "add_path",
    "exclude_path",
    "suffix",
    "exclude_suf",
    "hdr_flags",
    "path_flags",
    "blank_flags",
    "first_flags",
    "urls",
    "url_scrape",
    "git_path",
    "git_exclude",
    "replace_rules",
    "preserve_rules",
}

_BOOL_ATTRS: Set[str] = {
    "rm_comments",
    "no_rm_comments",
    "rm_import",
    "rm_export",
    "keep_blank",
    "list_only",
    "absolute_path",
    "skip_headers",
    "keep_header",
    "preserve_cache",
    "strip_html",
    "to_stdout",
    "url_cross_domain",
}

_STR_ATTRS: Set[str] = {
    "workdir",
    "workspace",
    "template",
    "wrap_lang",
    "child_template",
    "ai_model",
    "ai_system_prompt",
    "ai_seeds",
    "ai_reasoning_effort",
}

_FLT_ATTRS: Set[str] = {
    "ai_temperature",
    "ai_top_p",
    "ai_presence_penalty",
    "ai_frequency_penalty",
}

_NON_INHERITED: Set[str] = {"output", "unwrap", "ai", "template"}

__all__ = [
    "_INT_ATTRS",
    "_LIST_ATTRS",
    "_BOOL_ATTRS",
    "_STR_ATTRS",
    "_FLT_ATTRS",
    "_NON_INHERITED",
    "_VALUE_FLAGS",
]