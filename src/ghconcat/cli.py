#!/usr/bin/env python3
"""
ghconcat – hierarchical, language-agnostic concatenation & templating tool.

Gaheos – https://gaheos.com
Copyright (c) 2025 GAHEOS S.A.
Copyright (c) 2025 Leonardo Gavidia Guerra <leo@gaheos.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# SPDX-FileCopyrightText: 2025 GAHEOS S.A.
# SPDX-FileCopyrightText: 2025 Leonardo Gavidia Guerra
# SPDX-License-Identifier: AGPL-3.0-or-later

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, NoReturn
import logging
import ssl

from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
from ghconcat.io.walker import WalkerAppender
from ghconcat.io.readers import get_global_reader_registry, ReaderRegistry
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.processing.envctx import EnvContext
from ghconcat.parsing.directives import DirNode, DirectiveParser
from ghconcat.parsing.flags import VALUE_FLAGS as _VALUE_FLAGS
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.rendering.path_resolver import DefaultPathResolver
from ghconcat.rendering.renderer import Renderer as _Renderer
from ghconcat.ai.ai_processor import DefaultAIProcessor
from ghconcat.parsing.tokenize import inject_positional_add_paths
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.discovery.file_discovery import FileDiscovery

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ghconcat")

# ───────────────────────────────  Constants  ────────────────────────────────

HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"

_LINE1_RE: re.Pattern[str] = re.compile(r"^\s*#\s*line\s*1\d*\s*$")
_WORKSPACES_SEEN: set[Path] = set()

_LINE_OPS = LineProcessingService(
    comment_rules=COMMENT_RULES,
    line1_re=_LINE1_RE,
    logger=logger,
)
_INTERPOLATOR = StringInterpolator()

# ─────────────────────── “none” handling & env substitution  ────────────────


_INT_ATTRS: Set[str] = {
    "total_lines", "first_line",
    "url_scrape_depth",
    # NEW
    "ai_max_tokens",
}

_LIST_ATTRS: Set[str] = {
    "add_path", "exclude_path", "suffix", "exclude_suf",
    "hdr_flags", "path_flags", "blank_flags", "first_flags",
    "urls", "url_scrape", "git_path", "git_exclude",
    "replace_rules", "preserve_rules",
}

_BOOL_ATTRS: Set[str] = {
    "rm_simple", "rm_all", "rm_import", "rm_export",
    "keep_blank", "list_only", "absolute_path", "skip_headers",
    "keep_header", "disable_url_domain_only", "preserve_cache"
}

_STR_ATTRS: Set[str] = {
    "workdir", "workspace", "template", "wrap_lang", "child_template",
    "ai_model", "ai_system_prompt", "ai_seeds",
    # NEW
    "ai_reasoning_effort",
}

_FLT_ATTRS: Set[str] = {
    "ai_temperature",
    "ai_top_p",
    "ai_presence_penalty",
    "ai_frequency_penalty",
}

_NON_INHERITED: Set[str] = {"output", "unwrap", "ai", "template"}
_GIT_CLONES: Dict[Tuple[str, str | None], Path] = {}
_RE_DELIM: str = "/"
_TEXT_TRANSFORMER = TextTransformer(logger=logger, regex_delim=_RE_DELIM)
_ENV_CONTEXT = EnvContext(logger=logger)


def _ssl_ctx_for(url: str) -> Optional[ssl.SSLContext]:
    """
    Build an SSL context for *url* honoring the environment variable:

        GHCONCAT_INSECURE_TLS=1  → disables certificate verification.

    If the flag is not set or the URL is not HTTPS, returns None (default context).
    """
    if not url.lower().startswith("https"):
        return None
    if os.getenv("GHCONCAT_INSECURE_TLS") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


# ─────────────────────── argparse builder (no “‑X”)  ────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    """
    Construct and return an `argparse.ArgumentParser` instance for **one**
    context block.  The parser intentionally omits any legacy GAHEOS v1
    switches and follows GAHEOS v2 semantics exclusively.
    """
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [-x FILE] … [OPTIONS]",
        add_help=False,
        description=(
            "ghconcat – multi-level concatenation, slicing & templating tool\n"
            "Everything after a “-x FILE” is parsed inside the directive-file "
            "context unless another “-x” is encountered."
        ),
    )

    g_loc = p.add_argument_group("Discovery")
    g_rng = p.add_argument_group("Line slicing")
    g_cln = p.add_argument_group("Cleaning")
    g_sub = p.add_argument_group("Substitution")
    g_tpl = p.add_argument_group("Template & output")
    g_ai = p.add_argument_group("AI integration")
    g_misc = p.add_argument_group("Miscellaneous")

    g_loc.add_argument(
        "-w", "--workdir", metavar="DIR", dest="workdir",
        help=(
            "Root directory that will be *scanned for content files* in the current "
            "context.  If omitted, the search starts at the current working directory. "
            "Any other relative path (templates, outputs, “‑a PATH”, etc.) is first "
            "resolved against this directory unless a parent context re‑defines it."
        ),
    )
    g_loc.add_argument(
        "-W", "--workspace", metavar="DIR", dest="workspace",
        help=(
            "Folder that holds *templates, prompts, AI artefacts and outputs*.  "
            "Defaults to the current ‑w directory.  Paths given to ‑o/‑t/‑‑ai‑* are "
            "resolved here, keeping project sources and generated files separated."
        ),
    )
    g_loc.add_argument(
        "-a", "--add-path", metavar="PATH", action="append", dest="add_path",
        help=(
            "Add a file **or** directory (recursively) to the inclusion set.  "
            "May be repeated.  Bare CLI tokens that do *not* start with “‑” are "
            "implicitly converted to this flag, so `ghconcat src utils` equals "
            "`ghconcat -a src -a utils`."
        ),
    )
    g_loc.add_argument(
        "-A", "--exclude-path", metavar="DIR", action="append", dest="exclude_path",
        help=(
            "Exclude an entire directory subtree from discovery, overriding any "
            "broader inclusion rule.  Repeatable and honoured *before* suffix filters."
        ),
    )
    g_loc.add_argument(
        "-f", "--url", metavar="URL", action="append", dest="urls",
        help=(
            "Download a single remote resource and cache it under "
            "<workspace>/.ghconcat_urlcache.  Its contents are then processed as if "
            "it were a local file, subject to the same suffix, slicing and cleaning "
            "rules that apply to files added with ‑a."
        ),
    )
    g_loc.add_argument(
        "-F", "--url-scrape", metavar="URL", action="append", dest="url_scrape",
        help=(
            "Start a *depth‑limited crawler* at each seed URL, downloading every "
            "linked resource that matches the current suffix / exclusion filters.  "
            "Links with no extension are assumed to be “.html” for filtering purposes."
        ),
    )
    g_loc.add_argument(
        "-d", "--url-scrape-depth", metavar="N", type=int,
        dest="url_scrape_depth", default=2,
        help=(
            "Maximum recursion depth for ‑F/‑‑url‑scrape (default: 2).  "
            "`0` means scrape only the seed page itself, without following links."
        ),
    )
    g_loc.add_argument(
        "-D", "--disable-same-domain", action="store_true",
        dest="disable_url_domain_only",
        help=(
            "Allow the scraper (‑F) to follow links *outside* the seed’s scheme+host.  "
            "Without this flag, ghconcat remains confined to the original domain."
        ),
    )
    g_loc.add_argument(
        "-g", "--git-path", metavar="SPEC", action="append", dest="git_path",
        help=(
            "Include sources from a remote *Git* repository.  "
            "SPEC → URL[^BRANCH][/SUBPATH].  If BRANCH is omitted the default "
            "branch is used; if SUBPATH is omitted the whole repository is scanned."
        ),
    )
    g_loc.add_argument(
        "-G", "--git-exclude", metavar="SPEC", action="append", dest="git_exclude",
        help="Exclude a file or subtree inside a repository previously added with -g.",
    )
    g_loc.add_argument(
        "-s", "--suffix", metavar="SUF", action="append", dest="suffix",
        help=(
            "Whitelist extensions (e.g. “.py”).  If at least one ‑s is present, the "
            "suffix filter becomes *positive* (everything else is ignored unless "
            "explicitly whitelisted by another rule).  Repeatable."
        ),
    )
    g_loc.add_argument(
        "-S", "--exclude-suffix", metavar="SUF", action="append", dest="exclude_suf",
        help=(
            "Blacklist extensions irrespective of origin (local or remote).  "
            "An explicit file added with ‑a always wins over an exclusion suffix."
        ),
    )

    g_rng.add_argument(
        "-n", "--total-lines", metavar="NUM", type=int, dest="total_lines",
        help=(
            "Keep at most NUM lines from each file *after* header adjustments.  "
            "Combine with ‑N to create sliding windows."
        ),
    )
    g_rng.add_argument(
        "-N", "--start-line", metavar="LINE", type=int, dest="first_line",
        help=(
            "Start concatenation at 1‑based line LINE.  Headers before this line are "
            "kept or removed according to ‑m / ‑M."
        ),
    )
    g_rng.add_argument(
        "-m", "--keep-first-line", dest="first_flags",
        action="append_const", const="keep",
        help=(
            "Always retain the very first physical line (shebang, encoding cookie, "
            "XML prolog, etc.) even if slicing starts after it."
        ),
    )
    g_rng.add_argument(
        "-M", "--no-first-line", dest="first_flags",
        action="append_const", const="drop",
        help="Force‑drop the first physical line regardless of other slicing flags.",
    )
    g_sub.add_argument(
        "-y", "--replace", metavar="SPEC", action="append",
        dest="replace_rules",
        help=(
            "Delete or substitute *text fragments* that match SPEC.  The syntax is "
            "strictly `/pattern/`    → delete matches, or\n"
            "         `/patt/repl/flags` where flags ∈ {g,i,m,s}.  Delimiter is `/` "
            "and may be escaped inside the pattern/replacement with `\\/`.  The "
            "pattern is a Python‑style regex.  Invalid patterns are logged and "
            "silently ignored."
        ),
    )
    g_sub.add_argument(
        "-Y", "--preserve", metavar="SPEC", action="append",
        dest="preserve_rules",
        help=(
            "Regex exceptions for `-y`.  Any region matched by a PRESERVE rule is "
            "temporarily shielded from the replace engine and restored afterwards.  "
            "Same delimiter, escaping and flag rules as `-y`."
        ),
    )

    g_cln.add_argument(
        "-c", "--remove-comments", action="store_true", dest="rm_simple",
        help="Remove *inline* comments while keeping full‑line comments intact.",
    )
    g_cln.add_argument(
        "-C", "--remove-all-comments", action="store_true", dest="rm_all",
        help="Remove **all** comments, including full‑line ones.",
    )
    g_cln.add_argument(
        "-i", "--remove-import", action="store_true", dest="rm_import",
        help="Strip `import`, `require`, `use`, `#include` statements as supported.",
    )
    g_cln.add_argument(
        "-I", "--remove-export", action="store_true", dest="rm_export",
        help="Strip `export` / `module.exports` declarations in JS/TS-like files.",
    )
    g_cln.add_argument(
        "-b", "--strip-blank", dest="blank_flags",
        action="append_const", const="strip",
        help="Delete blank lines left after cleaning.",
    )
    g_cln.add_argument(
        "-B", "--keep-blank", dest="blank_flags",
        action="append_const", const="keep",
        help="Preserve blank lines (overrides an inherited ‑b).",
    )
    g_cln.add_argument(
        "-K", "--textify-html", action="store_true", dest="strip_html",
        help="Convert every *.html* file to plain-text (tags removed) before concatenation.",
    )

    g_tpl.add_argument(
        "-t", "--template", metavar="FILE", dest="template",
        help=(
            "Render the current context through a minimalist Jinja-style template. "
            "Placeholders use single braces `{var}` and see per-context variables, "
            "`ghconcat_dump`, plus values set via -e/-E.  **Not inherited**."
        ),
    )
    g_tpl.add_argument(
        "-T", "--child-template", metavar="FILE", dest="child_template",
        help=(
            "Set a *default template for descendant contexts only*. Acts as if each "
            "child had provided its own `-t FILE`. In a given context:\n"
            "  • If both `-t` and `-T` are present, `-t` applies **locally** while "
            "    `-T` updates the default for **subsequent contexts**.\n"
            "  • A child may override the inherited `-T` by specifying its own `-t`, "
            "    or replace it for its own descendants by providing a new `-T`."
        ),
    )
    g_tpl.add_argument(
        "-o", "--output", metavar="FILE", dest="output",
        help=(
            "Write the *final* text to FILE (path resolved against the workspace).  "
            "If omitted at the root context, the result streams to STDOUT."
        ),
    )
    g_tpl.add_argument(
        "-O", "--stdout", action="store_true", dest="to_stdout",
        help=(
            "Always duplicate the final output to STDOUT, even when ‑o is present.  "
            "Useful for piping while still keeping an on‑disk copy."
        ),
    )
    g_tpl.add_argument(
        "-u", "--wrap", metavar="LANG", dest="wrap_lang",
        help=(
            "Wrap every file body in a fenced code‑block.  The info‑string defaults "
            "to LANG; pass an empty string to keep language‑less fences."
        ),
    )
    g_tpl.add_argument(
        "-U", "--no-wrap", action="store_true", dest="unwrap",
        help="Cancel any inherited ‑u/‑‑wrap directive in this child context.",
    )
    g_tpl.add_argument(
        "-h", "--header", dest="hdr_flags",
        action="append_const", const="show",
        help="Emit a heavy banner header before each *new* file (`===== path =====`).",
    )
    g_tpl.add_argument(
        "-H", "--no-headers", dest="hdr_flags",
        action="append_const", const="hide",
        help="Suppress banner headers in this scope (child contexts may re‑enable).",
    )
    g_tpl.add_argument(
        "-r", "--relative-path", dest="path_flags",
        action="append_const", const="relative",
        help="Show header paths relative to the current workdir (default).",
    )
    g_tpl.add_argument(
        "-R", "--absolute-path", dest="path_flags",
        action="append_const", const="absolute",
        help="Show header paths as absolute file‑system paths.",
    )
    g_tpl.add_argument(
        "-l", "--list", action="store_true", dest="list_only",
        help="List matching file paths **instead of** their contents (one per line).",
    )
    g_tpl.add_argument(
        "-L", "--no-list", action="store_true", dest="no_list",
        help="Disable an inherited list mode within this context.",
    )
    g_tpl.add_argument(
        "-e", "--env", metavar="VAR=VAL", action="append", dest="env_vars",
        help=(
            "Define a *local* placeholder visible **only** in the current context.  "
            "Placeholders may reference earlier ones using the `` syntax."
        ),
    )
    g_tpl.add_argument(
        "-E", "--global-env", metavar="VAR=VAL", action="append", dest="global_env",
        help=(
            "Define a *global* placeholder inherited by every descendant context.  "
            "May be overridden locally with ‑e."
        ),
    )

    g_ai.add_argument(
        "--ai", action="store_true",
        help=(
            "Send the rendered text to an OpenAI chat endpoint.  Requires "
            "`OPENAI_API_KEY` in the environment.  The AI reply is written to ‑o "
            "(or to a temp file if ‑o is absent) and exposed as `{_ia_ctx}`."
        ),
    )
    g_ai.add_argument(
        "--ai-model", metavar="MODEL", default=DEFAULT_OPENAI_MODEL, dest="ai_model",
        help="Chat model to use (default: o3).",
    )
    g_ai.add_argument(
        "--ai-temperature", type=float, metavar="NUM", dest="ai_temperature",
        help="Sampling temperature for non‑o* (like gpt‑4o, gpt‑5‑chat) models (range 0–2).",
    )
    g_ai.add_argument(
        "--ai-top-p", type=float, metavar="NUM", dest="ai_top_p",
        help="Top‑p nucleus sampling parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-presence-penalty", type=float, metavar="NUM", dest="ai_presence_penalty",
        help="Presence‑penalty parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-frequency-penalty", type=float, metavar="NUM", dest="ai_frequency_penalty",
        help="Frequency‑penalty parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-system-prompt", metavar="FILE", dest="ai_system_prompt",
        help="Template‑aware system prompt file to prepend to the chat.",
    )
    g_ai.add_argument(
        "--ai-seeds", metavar="FILE", dest="ai_seeds",
        help="JSONL file with seed messages to prime the chat.",
    )
    g_ai.add_argument(
        "--ai-max-tokens", type=int, metavar="NUM", dest="ai_max_tokens",
        help=(
            "Maximum output tokens. For reasoning models (o‑series, gpt‑5 base) "
            "maps to `max_output_tokens` (Responses API). For chat models "
            "(gpt‑4o*, gpt‑5‑chat*) maps to `max_tokens` (Chat Completions)."
        ),
    )
    g_ai.add_argument(
        "--ai-reasoning-effort", metavar="LEVEL", dest="ai_reasoning_effort",
        choices=("low", "medium", "high"),
        help=(
            "Reasoning effort for o‑series/gpt‑5 (Responses API). Ignored by chat "
            "models. Defaults to GHCONCAT_AI_REASONING_EFFORT or 'medium'."
        ),
    )
    g_misc.add_argument(
        "--preserve-cache",
        action="store_true",
        help="Keep the .ghconcat_*cache directories after finishing the run.",
    )
    g_misc.add_argument(
        "--upgrade", action="store_true",
        help="Self‑update ghconcat from the official GAHEOS repository into ~/.bin.",
    )
    g_misc.add_argument(
        "--help", action="help",
        help="Show this integrated help message and exit.",
    )

    return p


# ─────────────────────────────  Aux helpers  ────────────────────────────────
def _fatal(msg: str, code: int = 1) -> None:
    """Abort execution immediately with *msg* written to *stderr*."""
    logger.error(msg)
    sys.exit(code)


def _debug_enabled() -> bool:  # pragma: no cover
    """Utility guard to ease local debugging (`DEBUG=1`)."""
    return os.getenv("DEBUG") == "1"


def _apply_replacements(
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
) -> str:
    """
    Apply replacement and preserve rules to *text*.

    This thin wrapper delegates to TextTransformer to keep the implementation
    testable and reusable, while preserving the original function signature
    used across the codebase (e.g., injection into WalkerAppender).
    """
    return _TEXT_TRANSFORMER.apply_replacements(text, replace_specs, preserve_specs)


def _expand_tokens(tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
    """
    Expand a directive line in four steps:

    1) Collect -e/--env and -E/--global-env assignments.
    2) Resolve nested $VAR references among those assignments (deep interpolation).
    3) Substitute $VAR across all tokens, skipping values after -e/-E.
    4) Remove any flag whose value is the literal "none" (case-insensitive).

    Thin wrapper delegating the full pipeline to :class:`EnvContext`
    to ensure a single source of truth.
    """
    return _ENV_CONTEXT.expand_tokens(
        tokens,
        inherited_env,
        value_flags=_VALUE_FLAGS,
        none_value=TOK_NONE,
    )


# ───────────────────────  Namespace post‑processing  ────────────────────────
def _post_parse(ns: argparse.Namespace) -> None:
    """
    Normalize tri-state flags after `parse_args` has run.
    """
    # Blank-line policy
    flags = set(ns.blank_flags or [])
    ns.keep_blank = "keep" in flags or "strip" not in flags

    # First-line policy
    first = set(ns.first_flags or [])
    if "drop" in first:
        ns.keep_header = False
    else:
        ns.keep_header = "keep" in first

    # Header visibility
    hdr = set(ns.hdr_flags or [])
    ns.skip_headers = not ("show" in hdr and "hide" not in hdr)

    # Absolute / relative
    pathf = set(ns.path_flags or [])
    ns.absolute_path = "absolute" in pathf and "relative" not in pathf

    # Wrap fences
    if ns.unwrap:
        ns.wrap_lang = None

    # List / no-list override
    if getattr(ns, "no_list", False):
        ns.list_only = False


def _clean(
        lines: Iterable[str],
        ext: str,
        *,
        rm_simple: bool,
        rm_all: bool,
        rm_imp: bool,
        rm_exp: bool,
        keep_blank: bool,
) -> List[str]:
    """Apply comment / import / blank‑line filters to *lines* via service."""
    return _LINE_OPS.clean_lines(
        lines,
        ext,
        rm_simple=rm_simple,
        rm_all=rm_all,
        rm_imp=rm_imp,
        rm_exp=rm_exp,
        keep_blank=keep_blank,
    )


def _interpolate(tpl: str, mapping: Dict[str, str]) -> str:
    """
    Replace every *{placeholder}* in *tpl* with its value from *mapping*.

    This wrapper delegates to StringInterpolator to keep a single, tested
    implementation while preserving the public/legacy symbol for tests.
    """
    return _INTERPOLATOR.interpolate(tpl, mapping)


def _call_openai(
        prompt: str,
        out_path: Path,
        *,
        model: str,
        system_prompt: str,
        temperature: float | None,
        top_p: float | None,
        presence_pen: float | None,
        freq_pen: float | None,
        seeds_path: Optional[Path],
        timeout: int = 1800,
        # NEW:
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
) -> None:
    """
    Send *prompt* to OpenAI unless GHCONCAT_DISABLE_AI=1 – in that case write
    “AI‑DISABLED”.

    Notes
    -----
    • Keeps 1:1 compatibility with legacy behavior for the test-suite:
      - Honors GHCONCAT_DISABLE_AI.
      - Writes “⚠ OpenAI disabled” when SDK or API key is missing.
      - Accepts seeds JSONL and system prompt as before.
    • Delegates to :class:`OpenAIClient` and forwards optional `max_tokens`
      and `reasoning_effort` without breaking callers that ignore them.
    """
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return

    if not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return

    try:
        from ghconcat.ai.ai_client import OpenAIClient
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")
        return

    client = OpenAIClient(logger=logger)

    try:
        out_path.write_text(client.generate_chat_completion(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            presence_penalty=presence_pen,
            frequency_penalty=freq_pen,
            seeds_path=seeds_path,
            timeout=timeout,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


def _merge_ns(parent: argparse.Namespace, child: argparse.Namespace) -> argparse.Namespace:
    """
    Return a **new** namespace = parent ⊕ child (child overrides, lists extend).

    Important: this function does NOT resolve filesystem paths. Path resolution
    (especially for -w/--workdir and -W/--workspace) is performed in
    `_execute_node`, where we know the actual parent roots to correctly apply
    the semantics (CWD for level 0, workdir-relative workspace at level 0, and
    parent-root / parent-workspace for children).
    """
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

    # Do NOT pre-resolve 'workspace' here. Let _execute_node do it
    # with full context (cwd/root/workspace inheritance).
    ns = argparse.Namespace(**merged)
    _post_parse(ns)
    return ns


# ─────────────────────────────  Core executor  ──────────────────────────────
def _parse_env_items(items: Optional[List[str]]) -> Dict[str, str]:
    """
    Parse a homogeneous list of VAR=VAL items (e.g. from argparse) into a dict.

    Uses :class:`EnvContext` and `_fatal` for strict validation, preserving
    the original process-exit behavior on malformed entries.
    """
    return _ENV_CONTEXT.parse_items(items, on_error=lambda m: _fatal(m))


# ─────────────────────────────  Core executor  ──────────────────────────────
def _execute_node(
        node: DirNode,
        ns_parent: Optional[argparse.Namespace],
        *,
        level: int = 0,
        parent_root: Optional[Path] = None,
        parent_workspace: Optional[Path] = None,
        inherited_vars: Optional[Dict[str, str]] = None,
        gh_dump: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], str]:
    """
    Compatibility wrapper: delegates to the new ExecutionEngine. Behavior is
    strictly identical to the legacy implementation.  All helper functions,
    sets and constants from this module are injected to preserve semantics.

    Change (DI – ReaderRegistry per-run)
    ------------------------------------
    A per-run ReaderRegistry clone is now created and injected explicitly into:
      • WalkerAppender (via FileReadingService.read_lines)
      • ExecutionEngine (via `registry=` argument)

    This removes implicit global dependencies from file reading.
    """

    def _clone_registry_for_run() -> ReaderRegistry:
        g = get_global_reader_registry(logger)
        cloned = ReaderRegistry(default_reader=g.default_reader)
        for rule in getattr(g, "_rules", []):
            if getattr(rule, "predicate", None) is None and getattr(rule, "suffixes", None):
                cloned.register(list(rule.suffixes), rule.reader)  # type: ignore[attr-defined]
        cloned.set_default(g.default_reader)
        return cloned

    reg = _clone_registry_for_run()
    from ghconcat.io.file_reader_service import FileReadingService
    frs = FileReadingService(registry=reg, logger=logger)

    # Inject slice/clean functions from the dedicated service (no globals).
    walker = WalkerAppender(
        read_file_as_lines=frs.read_lines,  # explicit DI
        apply_replacements=_apply_replacements,  # textops
        slice_lines=_LINE_OPS.slice_lines,  # from LineProcessingService
        clean_lines=_LINE_OPS.clean_lines,  # from LineProcessingService
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
        logger=logger,
    )

    def _gm_factory(ws: Path) -> GitRepositoryManager:
        return GitRepositoryManager(ws, logger=logger, clones_cache=_GIT_CLONES)

    def _uf_factory(ws: Path) -> UrlFetcher:
        return UrlFetcher(ws, logger=logger, ssl_ctx_provider=_ssl_ctx_for)

    discovery = FileDiscovery(
        walker=walker,
        git_manager_factory=_gm_factory,
        url_fetcher_factory=_uf_factory,
        resolver=DefaultPathResolver(),  # explicit DI for tests
        logger=logger,
    )

    # Inject the new interpolator as a callable for templates
    renderer = _Renderer(
        walker=walker,
        interpolate=_INTERPOLATOR.interpolate,
        header_delim=HEADER_DELIM,
        logger=logger,
    )

    _call_fn = (_call_openai if "ghconcat" not in sys.modules
                else getattr(sys.modules["ghconcat"], "_call_openai"))
    ai = DefaultAIProcessor(call_openai=_call_fn, logger=logger)

    engine = ExecutionEngine(
        parser_factory=_build_parser,
        post_parse=_post_parse,
        merge_ns=lambda parent, child: _merge_ns(parent, child),  # type: ignore[arg-type]
        expand_tokens=lambda toks, inherited_env: _expand_tokens(toks, inherited_env),
        parse_env_items=_parse_env_items,
        resolver=DefaultPathResolver(),
        discovery=discovery,
        renderer=renderer,
        ai=ai,
        workspaces_seen=_WORKSPACES_SEEN,
        fatal=lambda msg: _fatal(msg),
        logger=logger,
        registry=reg,  # <-- explicit per-run registry
    )

    return engine.execute_node(
        node,
        ns_parent,
        level=level,
        parent_root=parent_root,
        parent_workspace=parent_workspace,
        inherited_vars=inherited_vars,
        gh_dump=gh_dump,
    )


# ──────────────────────────  Self‑upgrade helper  ───────────────────────────
def _perform_upgrade() -> None:  # pragma: no cover
    """Pull latest version from GAHEOS/ghconcat and install into ~/.bin."""
    import stat

    tmp = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    dest = Path.home() / ".bin" / "ghconcat"
    repo = "git@github.com:GAHEOS/ghconcat.git"

    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", repo, str(tmp)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        src = next(tmp.glob("**/ghconcat.py"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
        logger.info(f"✔ Updated → {dest}")
    except Exception as exc:  # noqa: BLE001
        _fatal(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


def _purge_caches() -> None:
    """
    Remove every «.ghconcat_*cache» directory observed during execution
    (git + URL scraper), unless the session requested to preserve them.
    """
    patterns = (".ghconcat_gitcache", ".ghconcat_urlcache")
    for ws in _WORKSPACES_SEEN:
        for pat in patterns:
            tgt = ws / pat
            if tgt.exists():
                try:
                    shutil.rmtree(tgt, ignore_errors=True)
                    logger.info(f"🗑  cache removed → {tgt}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"⚠  could not delete {tgt}: {exc}")


# ────────────────────────────  Public API  ──────────────────────────────────
class GhConcat:
    """
    Programmatic entry-point.

    * When an explicit «-o» is present the file is written **and** also
      returned as a *str* for convenience.
    * Otherwise the in-memory dump is returned.
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute ghconcat over *argv* and return the concatenation result.

        Each «-x FILE» starts a completely isolated directive tree.
        Bare paths passed at the CLI level are implicitly converted into
        “-a PATH” arguments.
        """
        global _SEEN_FILES
        _SEEN_FILES = set()  # full reset per public call
        _GIT_CLONES.clear()

        units: List[Tuple[Optional[Path], List[str]]] = []
        cli_remainder: List[str] = []

        it = iter(argv)
        for tok in it:
            if tok in ("-x", "--directives"):
                try:
                    fpath = Path(next(it))
                except StopIteration:
                    _fatal("missing FILE after -x/--directives")
                if not fpath.exists():
                    _fatal(f"directive file {fpath} not found")
                units.append((fpath, inject_positional_add_paths(cli_remainder)))
                cli_remainder = []
            else:
                cli_remainder.append(tok)

        if not units:
            units.append((None, inject_positional_add_paths(cli_remainder)))
        elif cli_remainder:
            last_path, last_cli = units[-1]
            units[-1] = (last_path, last_cli + inject_positional_add_paths(cli_remainder))

        outputs: List[str] = []
        dparser = DirectiveParser(logger=logger)  # OO parser

        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()  # dedup scope per unit

            if directive_path:
                root = dparser.parse(directive_path)
                root.tokens.extend(extra_cli)
            else:
                root = DirNode()
                root.tokens.extend(extra_cli)

            if "--upgrade" in root.tokens:
                (_perform_upgrade if "ghconcat" not in sys.modules
                 else getattr(sys.modules["ghconcat"], "_perform_upgrade"))()

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if "--preserve-cache" not in argv:
            _purge_caches()

        return "".join(outputs)


def main() -> NoReturn:
    try:
        GhConcat.run(sys.argv[1:])
        raise SystemExit(0)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        if os.getenv("DEBUG") == "1":
            raise
        logger.error("Unexpected error: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
