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
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib
from copy import deepcopy
from hashlib import sha1
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import logging

try:
    from lxml import etree as _ET  # type: ignore

    _ET_PARSER = _ET.HTMLParser(recover=True)
except ModuleNotFoundError:  # lxml no instalado
    try:
        import xml.etree.ElementTree as _ET  # type: ignore

        _ET_PARSER = None  # ElementTree no necesita parser
    except ModuleNotFoundError:
        _ET = None  # sin ningún etree

# Optional OpenAI import (lazy)
try:
    import openai  # type: ignore
    from openai import OpenAIError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore


    class OpenAIError(Exception):  # type: ignore
        """Raised when the OpenAI SDK is unavailable."""

try:
    from pypdf import PdfReader  # extracción de texto incrustado
except ModuleNotFoundError:  # pragma: no cover
    PdfReader = None  # type: ignore

try:
    from pdf2image import convert_from_path  # rasterización para OCR
    import pytesseract  # OCR Tesseract
except ModuleNotFoundError:  # pragma: no cover
    convert_from_path = None  # type: ignore
    pytesseract = None

# ─────────────────────  Optional Excel import (lazy)  ──────────────────────
try:
    import pandas as _pd  # Excel reader (requires openpyxl | xlrd | pyxlsb)
    import io  # stdlib – for in-memory TSV
except ModuleNotFoundError:  # pragma: no cover
    _pd = None  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ghconcat")

# ───────────────────────────────  Constants  ────────────────────────────────
_TAG_RE = re.compile(r"<[^>]+>")
_CLI_MODE: bool = False
HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# Pattern used to wipe any “# line 1…” when the first line must be dropped.
_LINE1_RE: re.Pattern[str] = re.compile(r"^\s*#\s*line\s*1\d*\s*$")
_WORKSPACES_SEEN: set[Path] = set()

# This cache is *per GhConcat.run()*; it is cleared on each public entry call.
_SEEN_FILES: set[str] = set()
_COMMENT_RULES: Dict[str, Tuple[
    re.Pattern[str],  # simple comment
    re.Pattern[str],  # full‑line comment
    Optional[re.Pattern[str]],  # import‑like
    Optional[re.Pattern[str]],  # export‑like
]] = {
    # ─────────────  Scripting / dynamic  ─────────────
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

    # ─────────────  Static & systems  ─────────────
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

    # ─────────────  Data / markup  ─────────────
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

    # ─────────────  Miscellaneous / scientific  ─────────────
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

_RE_BLANK: re.Pattern[str] = re.compile(r"^\s*$")
_PLACEHOLDER: re.Pattern[str] = re.compile(
    r"(?<!\{)\{([a-zA-Z_]\w*)}(?!})"
)
_ENV_REF: re.Pattern[str] = re.compile(r"\$([a-zA-Z_][\w\-]*)")

# ─────────────────────── “none” handling & env substitution  ────────────────
_VALUE_FLAGS: Set[str] = {
    "-w", "--workdir", "-W", "--workspace",
    "-a", "--add-path", "-A", "--exclude-path",
    "-g", "--git-path", "-G", "--git-exclude",
    "-f", "--url",
    "-F", "--url-scrape",
    "-d", "--url-scrape-depth",
    "-D", "--disable-same-domain",
    "-s", "--suffix", "-S", "--exclude-suffix",
    "-n", "--total-lines", "-N", "--start-line",
    "-t", "--template", "-o", "--output", "-T", "--child-template",
    "-u", "--wrap", "--ai-model", "--ai-system-prompt",
    "--ai-seeds", "--ai-temperature", "--ai-top-p",
    "--ai-presence-penalty", "--ai-frequency-penalty",
    "-e", "--env", "-E", "--global-env",
    "-y", "--replace", "-Y", "--preserve",
}
_INT_ATTRS: Set[str] = {
    "total_lines", "first_line",
    "url_scrape_depth",
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


# ───────────────────────────────  Data classes  ─────────────────────────────
class DirNode:
    """
    Simple tree container representing a “[context]” block inside a
    directive file.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name: Optional[str] = name
        self.tokens: List[str] = []
        self.children: List["DirNode"] = []


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

    # ── option groups (keep logical order) ────────────────────────────────
    g_loc = p.add_argument_group("Discovery")
    g_rng = p.add_argument_group("Line slicing")
    g_cln = p.add_argument_group("Cleaning")
    g_sub = p.add_argument_group("Substitution")
    g_tpl = p.add_argument_group("Template & output")
    g_ai = p.add_argument_group("AI integration")
    g_misc = p.add_argument_group("Miscellaneous")

    # ── discovery ────────────────────────────────────────────────────────────
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

    # ── line slicing ──────────────────────────────────────────────────────────
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

    # ── cleaning ──────────────────────────────────────────────────────────────
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

    # ── template & output ─────────────────────────────────────────────────────
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
            "Placeholders may reference earlier ones using the `$VAR` syntax."
        ),
    )
    g_tpl.add_argument(
        "-E", "--global-env", metavar="VAR=VAL", action="append", dest="global_env",
        help=(
            "Define a *global* placeholder inherited by every descendant context.  "
            "May be overridden locally with ‑e."
        ),
    )

    # ── AI integration ────────────────────────────────────────────────────────
    g_ai.add_argument(
        "--ai", action="store_true",
        help=(
            "Send the rendered text to an OpenAI chat endpoint.  Requires "
            "`OPENAI_API_KEY` in the environment.  The AI reply is written to ‑o "
            "(or to a temp file if ‑o is absent) and exposed as `{_ia_ctx}`."
        ),
    )
    g_ai.add_argument(
        "--ai-model", metavar="MODEL", default=DEFAULT_OPENAI_MODEL,
        help="Chat model to use (default: o3).",
    )
    g_ai.add_argument(
        "--ai-temperature", type=float, metavar="NUM",
        help="Sampling temperature for non‑o* (like o3 o4-mini) models (range 0–2).",
    )
    g_ai.add_argument(
        "--ai-top-p", type=float, metavar="NUM",
        help="Top‑p nucleus sampling parameter.",
    )
    g_ai.add_argument(
        "--ai-presence-penalty", type=float, metavar="NUM",
        help="Presence‑penalty parameter.",
    )
    g_ai.add_argument(
        "--ai-frequency-penalty", type=float, metavar="NUM",
        help="Frequency‑penalty parameter.",
    )
    g_ai.add_argument(
        "--ai-system-prompt", metavar="FILE",
        help="Template‑aware system prompt file to prepend to the chat.",
    )
    g_ai.add_argument(
        "--ai-seeds", metavar="FILE",
        help="JSONL file with seed messages to prime the chat.",
    )

    # ── miscellaneous ─────────────────────────────────────────────────────────
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


def _is_within(path: Path, parent: Path) -> bool:
    """Return *True* if *path* is contained in *parent* (ancestor check)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _inject_positional_add_paths(tokens: List[str]) -> List[str]:
    """
    Expand every bare *token* that does **not** start with “-” into
    the pair ``["-a", token]``.

    Reglas:
    • Respeta los flags que esperan valor (p.ej. “-o FILE”) manteniendo
      su siguiente token intacto.
    • No altera tokens que empiezan por «-».
    """
    out: List[str] = []
    expect_value = False
    for tok in tokens:
        if expect_value:  # valor de un flag previo
            out.append(tok)
            expect_value = False
            continue

        if tok.startswith("-"):  # es otro flag
            out.append(tok)
            if tok in _VALUE_FLAGS:
                expect_value = True  # el siguiente token es su argumento
            continue

        # Token posicional → equivale a “-a PATH”
        out.extend(["-a", tok])
    return out


# ───────────────────────  Directive‑file parsing  ───────────────────────────
def _tokenize_directive_line(raw: str) -> List[str]:
    """
    Split *raw* (a single line from a directive file) into CLI-style tokens,
    honouring `//`, `#` and `;` as inline-comment delimiters **except** when
    the `//` belongs to a URI scheme such as `https://`, `s3://`, `file://`,
    etc.

    - Bare tokens whose first char is *not* “-” are implicitly expanded to
      “-a <token>” for convenience.
    """

    def _strip_inline_comments(line: str) -> str:
        in_quote: str | None = None
        i = 0
        n = len(line)

        while i < n:
            ch = line[i]

            # ──────────────────────────────────────────────────────
            #  Handle simple quoting to ignore markers inside them
            # ──────────────────────────────────────────────────────
            if ch in {"'", '"'}:
                if in_quote is None:
                    in_quote = ch
                elif in_quote == ch:
                    in_quote = None
                i += 1
                continue

            # ──────────────────────────────────────────────────────
            #  Comment markers are recognised **only** when unquoted
            # ──────────────────────────────────────────────────────
            if in_quote is None:
                # 1) “//”  → comment  (but NOT when preceded by ':')
                #    i.e. the triple “://” inside a URI is *not* a comment.
                if ch == "/" and i + 1 < n and line[i + 1] == "/":
                    if i == 0 or line[i - 1] != ":":  # real comment
                        return line[:i]
                    # else: part of   scheme://   → keep going

                # 2) “#”  → comment   (YAML / shell style)
                elif ch == "#":
                    return line[:i]

                # 3) “;”  → comment   (Makefile / SQL style)
                elif ch == ";":
                    return line[:i]

            i += 1
        return line  # no comment detected

    stripped = _strip_inline_comments(raw).strip()
    if not stripped:
        return []

    parts = shlex.split(stripped)
    if not parts:
        return []

    # Auto-expand positional paths → “-a PATH”
    if not parts[0].startswith("-"):
        tokens: List[str] = []
        for pth in parts:
            tokens.extend(["-a", pth])
        return tokens

    return parts


def _html_to_text(src: str) -> str:
    """
    Devuelve una versión en **texto plano** de *src* (documento o fragmento HTML).

    - **lxml.etree** : `etree.fromstring(..., parser)`  → `itertext()`.
    - **xml.etree.ElementTree** : igual pero sin parser.
    - **Fallback**              : quita todas las etiquetas con regex y colapsa espacios.
    """
    if _ET is None:  # 3) último recurso
        return re.sub(r"[ \t]+\n", "\n",
                      _TAG_RE.sub(" ", src)).strip()

    try:  # 1) lxml  o  2) ElementTree
        root = (_ET.fromstring(src, parser=_ET_PARSER)  # type: ignore[arg-type]
                if _ET_PARSER is not None
                else _ET.fromstring(src))
        # Únete preservando saltos razonables
        return "\n".join(t for t in root.itertext() if t.strip())
    except Exception:
        # Si el parser falla (HTML muy roto) → fallback regex
        return re.sub(r"[ \t]+\n", "\n",
                      _TAG_RE.sub(" ", src)).strip()


def _git_cache_root(workspace: Path) -> Path:
    """
    Return the directory that stores shallow clones of remote repositories,
    creating it if it does not yet exist.
    """
    root = workspace / ".ghconcat_gitcache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parse_git_spec(spec: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse a `-g / -G` SPEC and return **(repo_url, branch, sub_path)**.

    • `repo_url`  – Canonical URL for `git clone` (guaranteed to end in `.git`).
    • `branch`    – Specified branch or *None* for the default branch.
    • `sub_path`  – File/dir inside the repo, relative (no leading slash) or *None*.

    The syntax accepted is::

        URL[ ^BRANCH ][ /SUBPATH ]

    Examples
    --------
    >>> _parse_git_spec("git@github.com:GAHEOS/ghconcat")
    ('git@github.com:GAHEOS/ghconcat.git', None, None)

    >>> _parse_git_spec("https://github.com/org/repo^dev/src")
    ('https://github.com/org/repo.git', 'dev', 'src')
    """
    # 1) Branch split
    if "^" in spec:
        url_part, tail = spec.split("^", 1)
        if "/" in tail:
            branch, sub_path = tail.split("/", 1)
            sub_path = sub_path.lstrip("/")  # ← NUEVO
        else:
            branch, sub_path = tail, None
    else:
        url_part, branch, sub_path = spec, None, None

    # 2) Extract sub‑path when no ^BRANCH was given
    if sub_path is None:
        if url_part.startswith("http"):
            parsed = urllib.parse.urlparse(url_part)
            segs = parsed.path.lstrip("/").split("/")
            if len(segs) > 2:  # /owner/repo/[…]
                sub_path = "/".join(segs[2:])
                url_part = parsed._replace(
                    path="/" + "/".join(segs[:2])
                ).geturl()
        elif url_part.startswith("git@"):
            host, path = url_part.split(":", 1)
            segs = path.split("/")
            if len(segs) > 2:
                sub_path = "/".join(segs[2:])
                url_part = f"{host}:{'/'.join(segs[:2])}"

    # 3) Ensure .git suffix for HTTPS; git@ usually already works without it.
    if url_part.startswith("http") and not url_part.endswith(".git"):
        url_part += ".git"

    return url_part, branch, sub_path


def _clone_git_repo(repo_url: str, branch: Optional[str], cache_root: Path) -> Path:
    """
    Clone *repo_url* (shallow) into *cache_root* unless an identical copy
    already exists.  Returns the path to the checked‑out work‑tree.
    """
    key = (repo_url, branch)

    if key in _GIT_CLONES:
        cached = _GIT_CLONES[key]
        if cached.exists():  # sigue en disco → OK
            return cached
        # El directorio fue borrado: elimina la entrada y clona de nuevo
        del _GIT_CLONES[key]

    digest = sha1(f"{repo_url}@{branch or 'HEAD'}".encode()).hexdigest()[:12]
    dst = cache_root / digest

    if not dst.exists():  # First time – do the network fetch
        try:
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd += ["--branch", branch, "--single-branch"]
            cmd += [repo_url, str(dst)]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"✔ cloned {repo_url} ({branch or 'default'}) → {dst}")
        except Exception as exc:  # noqa: BLE001
            _fatal(f"could not clone {repo_url}: {exc}")

    _GIT_CLONES[key] = dst
    return dst


def _collect_git_files(
        git_specs: List[str] | None,
        git_exclude_specs: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
) -> List[Path]:
    """
    Resolve every “-g / -G” SPEC into concrete filesystem paths.

    • NO archivo dentro de «.git/» se incluye jamás.
    • El directorio «.ghconcat_gitcache» *no* se considera “oculto” para
      esta rutina: sólo se descartan hijos que empiecen por «.git» o «.».

    The algorithm replicates (ligeramente simplificado) la lógica de
    `_gather_files`, pero sin el filtro global `_hidden()` que eliminaba
    el repositorio entero por vivir bajo «.ghconcat_gitcache».
    """
    if not git_specs:
        return []

    # ── 1. Preparación ───────────────────────────────────────────────────
    cache_root = _git_cache_root(workspace)
    include_roots: list[Path] = []
    exclude_roots: list[Path] = []

    # suffix →  “.py”  (garantiza punto al inicio)
    incl_suf = {s if s.startswith(".") else f".{s}" for s in suffixes}
    excl_suf = {s if s.startswith(".") else f".{s}" for s in exclude_suf} - incl_suf

    # ── 2. Clonado / path-resolution ─────────────────────────────────────
    for spec in git_specs:
        repo, branch, sub = _parse_git_spec(spec)
        root = _clone_git_repo(repo, branch, cache_root)
        include_roots.append(root / sub if sub else root)

    for spec in git_exclude_specs or []:
        repo, branch, sub = _parse_git_spec(spec)
        root = _clone_git_repo(repo, branch, cache_root)
        exclude_roots.append(root / sub if sub else root)

    excl_files = {p.resolve() for p in exclude_roots if p.is_file()}
    excl_dirs = {p.resolve() for p in exclude_roots if p.is_dir()}

    # ── 3. Recorrido manual ──────────────────────────────────────────────
    collected: set[Path] = set()

    def _skip_suffix(p: Path) -> bool:
        if incl_suf and not any(p.name.endswith(s) for s in incl_suf):
            return True
        if any(p.name.endswith(s) for s in excl_suf):
            return True
        return False

    for root in include_roots:
        if not root.exists():
            anc = next((p for p in root.parents if p.exists()), None)
            if anc is None:
                logger.warning(f"⚠  {root} does not exist – skipped")
                continue
            logger.debug(f"↪  {root} missing, walking ancestor {anc}")
            root = anc

        if root.is_file():
            if root.resolve() not in excl_files and not _skip_suffix(root):
                collected.add(root.resolve())
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            # descarta sub-árboles excluidos por «-G»
            dirnames[:] = [
                d for d in dirnames
                if (Path(dirpath, d).resolve() not in excl_dirs)
                   and d != ".git"  # nunca entrar al repo interno
            ]

            for fn in filenames:
                fp = Path(dirpath, fn)
                if fp.suffix in {".pyc", ".pyo"}:  # binarios Python
                    continue
                if fp.resolve() in excl_files:
                    continue
                if _skip_suffix(fp):
                    continue
                collected.add(fp.resolve())

    return sorted(collected, key=str)


def _parse_replace_spec(spec: str) -> tuple[re.Pattern[str], str, bool] | None:
    """
    Parse a *-y / -Y* SPEC and return a tuple *(regex, replacement, global_flag)*.

    Examples
    --------
    * `/foo/`           → delete  (replacement = '')           , global = True
    * `/foo/bar/gi`     → replace, IGNORECASE + global
    * '/path\\/to/--/'  → pattern = r'path/to', replacement='--'

    Returns *None* if the SPEC is syntactically invalid or the regex
    cannot be compiled.  Any error is logged at WARNING level and ignored,
    as mandated by the requirements.
    """
    # Strip optional outer quotes (single or double)
    if (spec.startswith(("'", '"')) and spec.endswith(spec[0])):
        spec = spec[1:-1]

    if not spec.startswith(_RE_DELIM):
        logger.warning(f"⚠  invalid replace spec (missing leading /): {spec!r}")
        return None

    # ── 1. Split spec into parts, honouring backslash escapes ────────────
    parts: list[str] = []
    buf: list[str] = []
    escaped = False
    for ch in spec[1:]:  # skip first delimiter
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == _RE_DELIM:  # unescaped delimiter  →  new part
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))  # tail (flags or empty)

    if len(parts) not in {2, 3}:  # pattern / [replacement] / [flags]
        logger.warning(f"⚠  invalid replace spec: {spec!r}")
        return None

    pattern_src = parts[0]
    replacement = "" if len(parts) == 2 else parts[1]
    flags_src = parts[-1] if len(parts) == 3 else "g"

    # ── 2. Build re flags + global switch ────────────────────────────────
    re_flags = 0
    global_sub = "g" in flags_src
    if "i" in flags_src:
        re_flags |= re.IGNORECASE
    if "m" in flags_src:
        re_flags |= re.MULTILINE
    if "s" in flags_src:
        re_flags |= re.DOTALL

    try:
        regex = re.compile(pattern_src, flags=re_flags)
    except re.error as exc:
        logger.warning(f"⚠  invalid regex in spec {spec!r}: {exc}")
        return None

    return regex, replacement, global_sub


def _apply_replacements(
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
) -> str:
    """
    Apply *replace_specs* to *text* while protecting regions matched by
    *preserve_specs*.  Preserved regions are temporarily swapped out with
    sentinel tokens and restored after all substitutions.

    Parameters
    ----------
    text:
        Original input text.
    replace_specs / preserve_specs:
        Sequences of raw SPEC strings exactly as provided on the CLI.

    Returns
    -------
    str
        The transformed text.
    """
    if not replace_specs:
        return text

    # ── 1. Compile rules (ignore invalid ones) ───────────────────────────
    replace_rules: list[tuple[re.Pattern[str], str, bool]] = []
    for spec in replace_specs:
        parsed = _parse_replace_spec(spec)
        if parsed:
            replace_rules.append(parsed)

    preserve_rules: list[re.Pattern[str]] = []
    for spec in preserve_specs or []:
        parsed = _parse_replace_spec(spec)
        if parsed:
            preserve_rules.append(parsed[0])  # only regex part needed

    if not replace_rules:
        return text

    # ── 2. Shield preserved regions  -------------------------------------
    placeholders: dict[str, str] = {}

    def _shield(match: re.Match[str]) -> str:
        token = f"\x00GHPRS{len(placeholders)}\x00"
        placeholders[token] = match.group(0)
        return token

    for rx in preserve_rules:
        text = rx.sub(_shield, text)

    # ── 3. Apply replacements  -------------------------------------------
    for rx, repl, is_global in replace_rules:
        count = 0 if is_global else 1
        text = rx.sub(repl, text, count=count)

    # ── 4. Restore preserved regions  ------------------------------------
    for token, original in placeholders.items():
        text = text.replace(token, original)

    return text


# ───────────────────────────  Lectura universal de archivos  ────────────────────────────
def _extract_pdf_text(
        pdf_path: Path,
        *,
        ocr_if_empty: bool = True,
        dpi: int = 300,
) -> str:
    """
    Devuelve TODO el texto plano de *pdf_path*.

    · **pypdf** se usa primero para extraer texto incrustado.
    · Si no hay texto y *ocr_if_empty* es True, intenta OCR con
      **pdf2image + pytesseract**.
    · Si las dependencias faltan, se registra un WARNING y se devuelve "".
    """
    # 1) Dependencias mínimas
    if PdfReader is None:
        logger.warning("✘ %s: instala `pypdf` para habilitar soporte PDF.", pdf_path)
        return ""

    try:
        reader = PdfReader(pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("✘ %s: fallo al abrir PDF (%s).", pdf_path, exc)
        return ""

    # 2) Texto embebido
    pages_text: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        txt = page.extract_text() or ""
        pages_text.append(txt.strip())
        logger.debug("PDF %s  · página %d → %d caracteres", pdf_path.name, idx, len(txt))

    full = "\n\n".join(pages_text).strip()
    if full or not ocr_if_empty:
        if not full:
            logger.warning("⚠ %s: sin texto incrustado.", pdf_path)
        return full

    # 3) Fallback OCR
    if convert_from_path is None or pytesseract is None:
        logger.warning(
            "✘ %s: OCR no disponible (pdf2image/pytesseract faltan).", pdf_path
        )
        return ""

    logger.info("⏳ OCR (%d pág.) → %s", len(reader.pages), pdf_path.name)
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        ocr_chunks = [pytesseract.image_to_string(img) for img in images]
        return "\n\n".join(chunk.strip() for chunk in ocr_chunks)
    except Exception as exc:  # noqa: BLE001
        logger.error("✘ OCR falló en %s (%s).", pdf_path, exc)
        return ""


def _extract_excel_tsv(xls_path: Path) -> str:
    """
    Return a **tab-separated** textual dump of *every* sheet in *xls_path*.

    The routine tries to keep dependencies optional:
    • Requires `pandas` plus an Excel engine (openpyxl | xlrd | pyxlsb).
    • Each sheet is prefixed by «===== <sheet name> =====».
    • Empty cells become empty strings to preserve column alignment.
    • On any failure the function logs an error and returns an empty string,
      allowing ghconcat to continue gracefully.
    """
    if _pd is None:
        logger.warning("✘ %s: install `pandas` to enable Excel support.", xls_path)
        return ""

    tsv_chunks: list[str] = []
    try:
        with _pd.ExcelFile(xls_path) as xls:
            for sheet in xls.sheet_names:
                try:
                    df = xls.parse(sheet, dtype=str)  # all values as str
                except Exception as exc:  # noqa: BLE001
                    logger.error("✘ %s: failed to parse sheet %s (%s).",
                                 xls_path, sheet, exc)
                    continue

                buf = io.StringIO()
                df.fillna("").to_csv(buf, sep="\t", index=False, header=True)
                tsv_chunks.append(f"===== {sheet} =====\n{buf.getvalue().strip()}")
    except Exception as exc:  # noqa: BLE001
        logger.error("✘ %s: failed to open Excel file (%s).", xls_path, exc)
        return ""

    return "\n\n".join(tsv_chunks)


def _read_file_as_lines(fp: Path) -> list[str]:
    """
    Return *fp* as a list of **text lines**:

    • PDF   → `_extract_pdf_text`
    • Excel → `_extract_excel_tsv` (all sheets, TSV)
    • Other → plain UTF-8 read with 'ignore' errors
    • Binary/undecodable files are skipped (empty list, logged)
    """
    suf = fp.suffix.lower()

    # ── PDF ────────────────────────────────────────────────────────────────
    if suf == ".pdf":
        txt = _extract_pdf_text(fp)
        return [ln + "\n" for ln in txt.splitlines()] if txt else []

    # ── Excel (.xls / .xlsx) ───────────────────────────────────────────────
    if suf in {".xls", ".xlsx"}:
        txt = _extract_excel_tsv(fp)
        return [ln + "\n" for ln in txt.splitlines()] if txt else []

    try:
        return fp.read_text(encoding="utf-8", errors="ignore").splitlines(True)
    except UnicodeDecodeError:
        logger.warning("✘ %s: binary or non-UTF-8 file skipped.", fp)
        return []


def _parse_directive_file(path: Path) -> DirNode:
    """
    Build a `DirNode` tree out of the *path* directive file.
    """
    root = DirNode()
    current = root

    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            stripped = raw.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                ctx_name = stripped.strip("[]").strip()
                node = DirNode(ctx_name)
                root.children.append(node)
                current = node
                continue

            line_toks = _tokenize_directive_line(raw)
            if line_toks:
                current.tokens.extend(line_toks)
    return root


def _strip_none(tokens: List[str]) -> List[str]:
    """
    Remove *both* a flag and its value when the value is literally “none”.
    """
    disabled: set[str] = set()
    i = 0
    while i + 1 < len(tokens):
        if tokens[i] in _VALUE_FLAGS and tokens[i + 1].lower() == TOK_NONE:
            disabled.add(tokens[i])
            i += 2
        else:
            i += 1

    cleaned: List[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _VALUE_FLAGS and tok in disabled:
            skip_next = True
            continue
        cleaned.append(tok)
    return cleaned


def _substitute_env(tokens: List[str], env_map: Dict[str, str]) -> List[str]:
    """
    Replace every «$VAR» occurrence with its value from *env_map*.
    Missing variables are expanded into an empty string.
    """
    out: List[str] = []
    skip_value = False
    for tok in tokens:
        if skip_value:
            out.append(tok)
            skip_value = False
            continue

        if tok in ("-e", "--env", "-E", "--global-env"):
            out.append(tok)
            skip_value = True
            continue

        out.append(_ENV_REF.sub(lambda m: env_map.get(m.group(1), ""), tok))
    return out


def _collect_env_from_tokens(tokens: Sequence[str]) -> Dict[str, str]:
    """
    Scan *tokens* and gather every definition that follows “‑e/‑E”.
    """
    env_map: Dict[str, str] = {}
    it = iter(tokens)
    for tok in it:
        if tok in ("-e", "--env", "-E", "--global-env"):
            try:
                kv = next(it)
            except StopIteration:
                _fatal(f"flag {tok} expects VAR=VAL")
            if "=" not in kv:
                _fatal(f"{tok} expects VAR=VAL (got '{kv}')")
            key, val = kv.split("=", 1)
            env_map[key] = val
    return env_map


def _expand_tokens(tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
    """
    Expand a directive line in four steps:

    1) Collect raw assignments provided via -e/--env and -E/--global-env.
    2) Resolve nested "$VAR" references among those assignments (deep interpolation).
       This ensures that variables defined from other variables become fully
       expanded *before* we touch the rest of the CLI tokens.
    3) Substitute "$VAR" across all tokens, skipping the immediate value after
       -e/-E so that the on-line definitions keep their literal text.
    4) Remove any flag whose value is the literal "none" (case-insensitive).
    """
    # Gather the raw env key-values present on the line plus inherited ones.
    env_all: Dict[str, str] = {**inherited_env, **_collect_env_from_tokens(tokens)}

    # NEW: make env values self-consistent (A uses B, B uses C, etc.) before
    # applying them to other tokens like -w/-W/-a.
    _refresh_env_values(env_all)

    # Perform $VAR substitution on the tokens (except the value right after -e/-E).
    expanded: List[str] = _substitute_env(tokens, env_all)

    # Finally, honor "none" to drop a flag together with its value.
    return _strip_none(expanded)


def _refresh_env_values(env_map: Dict[str, str]) -> None:
    """
    Re‑evaluate *env_map* until no “$VAR” references remain.

    This is performed after *raw‑concat*, *template* and *AI* stages, because
    those stages might add new variables that are referenced by others.
    """
    changed = True
    while changed:
        changed = False
        for key, val in list(env_map.items()):
            new_val = _ENV_REF.sub(lambda m: env_map.get(m.group(1), ""), val)
            if new_val != val:
                env_map[key] = new_val
                changed = True


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


# ─────────────────────────  Utility helpers  ────────────────────────────────
def _split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma‑ or space‑separated tokens."""
    if not raw:
        return []
    out: List[str] = []
    for itm in raw:
        out.extend([x for x in re.split(r"[,\s]+", itm) if x])
    return out


def _resolve_path(base: Path, maybe: Optional[str]) -> Path:
    """Resolve *maybe* against *base* unless it is already absolute."""
    if maybe is None:
        return base
    pth = Path(maybe).expanduser()
    return pth if pth.is_absolute() else (base / pth).resolve()


# ───────────────────────────  File discovery  ───────────────────────────────
def _hidden(p: Path) -> bool:
    """Return *True* for hidden files / directories (leading dot)."""
    return any(part.startswith(".") for part in p.parts)


def _gather_files(
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
) -> List[Path]:
    """
    Walk *add_path* and return every file that matches inclusion / exclusion
    rules. Explicit files always win.
    """
    collected: Set[Path] = set()

    explicit_files = [p for p in add_path if p.is_file()]
    dir_paths = [p for p in add_path if not p.is_file()]

    suffixes = [s if s.startswith(".") else f".{s}" for s in suffixes]
    exclude_suf = [s if s.startswith(".") else f".{s}" for s in exclude_suf]
    excl_set = set(exclude_suf) - set(suffixes)

    ex_dirs = {d.resolve() for d in exclude_dirs}

    def _dir_excluded(path: Path) -> bool:
        return any(_is_within(path, ex) for ex in ex_dirs)

    # Explicit files first
    for fp in explicit_files:
        collected.add(fp.resolve())

    for root in dir_paths:
        if not root.exists():
            logger.error(f"⚠  {root} does not exist – skipped")
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and not _dir_excluded(Path(dirpath, d))
            ]
            for fn in filenames:
                fp = Path(dirpath, fn)
                if _hidden(fp) or _dir_excluded(fp):
                    continue
                if suffixes and not any(fp.name.endswith(s) for s in suffixes):
                    continue
                if any(fp.name.endswith(s) for s in excl_set):
                    continue
                if fp.name.endswith((".pyc", ".pyo")):
                    continue
                collected.add(fp.resolve())

    return sorted(collected, key=str)


# ─────────────────────  Cleaning / slicing primitives  ──────────────────────
def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    """Return *True* if *line* must be discarded as a comment."""
    rules = _COMMENT_RULES.get(ext)
    return bool(rules and ((full and rules[1].match(line)) or (simple and rules[0].match(line))))


def _discard_import(line: str, ext: str, rm_imp: bool) -> bool:
    """Return *True* if *line* must be discarded because it is an import."""
    rules = _COMMENT_RULES.get(ext)
    return bool(rules and rm_imp and rules[2] and rules[2].match(line))


def _discard_export(line: str, ext: str, rm_exp: bool) -> bool:
    """Return *True* if *line* must be discarded because it is an export."""
    rules = _COMMENT_RULES.get(ext)
    return bool(rules and rm_exp and rules[3] and rules[3].match(line))


def _slice(
        raw: List[str],
        begin: Optional[int],
        total: Optional[int],
        keep_header: bool,
) -> List[str]:
    """
    Return a view of *raw* according to line-slicing flags.

    Bug-fix (2025-08-06): remove any “# line 1…” only when the slice
    **does not start at line 1** (start > 1) and the first line is dropped.
    """
    if not raw:
        return []

    start = max(1, begin or 1)
    end_excl = start - 1 + (total or len(raw) - start + 1)
    segment = raw[start - 1:end_excl]

    if keep_header and start > 1:
        segment = [raw[0], *segment]

    # Evita colisiones solo si el rango NO arranca en 1
    if not keep_header and start > 1:
        segment = [ln for ln in segment if not _LINE1_RE.match(ln)]

    return segment


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
    """Apply comment / import / blank‑line filters to *lines*."""
    out: List[str] = []
    for ln in lines:
        if _discard_comment(ln, ext, rm_simple, rm_all):
            continue
        if _discard_import(ln, ext, rm_imp):
            continue
        if _discard_export(ln, ext, rm_exp):
            continue
        if not keep_blank and _RE_BLANK.match(ln):
            continue
        out.append(ln)
    return out


# ─────────────────────────────  Concatenation  ──────────────────────────────
def _concat_files(
        files: list[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[list[tuple[str, str]]] = None,
) -> str:
    """
    Concatenate *files* applying cleaning, headers, optional wrapping and the
    new replace/preserve engine.
    """
    parts: list[str] = []

    for idx, fp in enumerate(files):
        ext = fp.suffix.lower()
        raw_lines = _read_file_as_lines(fp)

        if fp.suffix.lower() == ".pdf":
            ext = ""

        if ns.strip_html and fp.suffix.lower() == ".html":
            plain = _html_to_text("".join(raw_lines))
            raw_lines = [ln + "\n" for ln in plain.splitlines()]
            ext = ""

        body_lines = _clean(
            _slice(raw_lines, ns.first_line, ns.total_lines, ns.keep_header),
            ext,
            rm_simple=ns.rm_simple or ns.rm_all,
            rm_all=ns.rm_all,
            rm_imp=ns.rm_import,
            rm_exp=ns.rm_export,
            keep_blank=ns.keep_blank,
        )

        if ns.list_only:
            rel = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)
            parts.append(rel + "\n")
            continue

        if not body_lines or not "".join(body_lines).strip():
            continue

        hdr_path = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)

        # Banner header
        if not ns.skip_headers and hdr_path not in _SEEN_FILES:
            parts.append(f"{HEADER_DELIM}{hdr_path} {HEADER_DELIM}\n")
            _SEEN_FILES.add(hdr_path)

        body = "".join(body_lines)

        # ── REPLACEMENT ENGINE (nuevo) ────────────────────────────────────
        body = _apply_replacements(
            body,
            getattr(ns, "replace_rules", None),
            getattr(ns, "preserve_rules", None),
        )

        parts.append(body)

        if wrapped is not None:
            wrapped.append((hdr_path, body.rstrip()))

        if ns.keep_blank and (
                idx < len(files) - 1
                or (
                        idx == len(files) - 1
                        and ns.total_lines is None
                        and ns.first_line is None
                )
        ):
            parts.append("\n")

    return "".join(parts)


# ─────────────────────────────  AI helpers  ─────────────────────────────────
def _interpolate(tpl: str, mapping: Dict[str, str]) -> str:
    """
    Replace every *{placeholder}* in *tpl* with its value from *mapping*.

    Escaping rules
    --------------
    • ``{{literal}}``  → rendered as ``{literal}`` **without** interpolation.
    • Single-brace placeholders are interpolated only if *mapping* provides
      a value; otherwise they are replaced by the empty string (legacy
      behaviour).

    Parameters
    ----------
    tpl:
        Raw template string that may contain placeholders.
    mapping:
        Dictionary of values to substitute.

    Returns
    -------
    str
        The interpolated template where:
        1. ``{var}``      → mapping.get("var", "").
        2. ``{{content}}``→ ``{content}`` (verbatim, no interpolation).
    """
    # First pass: interpolate {var} placeholders that are *not* escaped.
    out: list[str] = []
    i = 0
    n = len(tpl)

    def _is_ident(s: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_]\w*", s))

    while i < n:
        # 1) Escapes «{{» y «}}»  → llave literal única
        if tpl.startswith("{{", i):
            out.append("{")
            i += 2
            continue
        if tpl.startswith("}}", i):
            out.append("}")
            i += 2
            continue

        # 2) Placeholder {var}
        if tpl[i] == "{":
            j = tpl.find("}", i + 1)
            if j != -1:
                candidate = tpl[i + 1: j]
                if _is_ident(candidate):
                    out.append(mapping.get(candidate, ""))
                    i = j + 1
                    continue
            # No placeholder válido → literal
        out.append(tpl[i])
        i += 1

    return "".join(out)


def _call_openai(  # pragma: no cover
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
) -> None:
    """
    Send *prompt* to OpenAI unless GHCONCAT_DISABLE_AI=1 – in that case write
    “AI‑DISABLED”.
    """
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return

    if openai is None or not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return

    client = openai.OpenAI()  # type: ignore[attr-defined]

    messages = (
        [{"role": "system", "content": system_prompt}] if system_prompt else []
    )
    if seeds_path and seeds_path.exists():
        for ln in seeds_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict) and {"role", "content"} <= obj.keys():
                    messages.append(
                        {"role": obj["role"], "content": obj["content"]}
                    )
                else:
                    messages.append({"role": "user", "content": ln.strip()})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": ln.strip()})

    messages.append({"role": "user", "content": prompt})

    params: Dict[str, object] = {"model": model, "messages": messages, "timeout": timeout}
    if not model.lower().startswith("o") or model.lower().startswith("gpt-5"):
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p
        if presence_pen is not None:
            params["presence_penalty"] = presence_pen
        if freq_pen is not None:
            params["frequency_penalty"] = freq_pen

    try:
        rsp = client.chat.completions.create(**params)  # type: ignore[arg-type]
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


def _fetch_urls(urls: List[str], cache_root: Path) -> List[Path]:
    """
    Download every *URL* into a temporary cache directory under *cache_root*
    and return a list of `Path` objects pointing to the downloaded files.

    • Preserves the original filename when present; otherwise uses
      “remote_<idx>[.ext]”, where *.ext* is inferred from Content-Type if
      available (e.g. text/html → .html, application/json → .json).
    • Emits one log line per successful fetch:  «✔ fetched URL → /path/file».
    • A minimal User-Agent header avoids 403 responses on stricter servers.
    • On any failure the URL is skipped and a warning is printed.
    """
    import urllib.request, urllib.parse, mimetypes, sys

    cache_dir = cache_root / ".ghconcat_urlcache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    _MIME_EXT_FALLBACK = {
        "text/html": ".html", "application/json": ".json",
        "text/css": ".css", "text/plain": ".txt", "text/xml": ".xml",
    }

    downloaded: List[Path] = []
    for idx, link in enumerate(urls):
        try:
            req = urllib.request.Request(
                link, headers={"User-Agent": "ghconcat/2.0 (+https://gaheos.com)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()

            raw_name = Path(urllib.parse.urlparse(link).path).name or f"remote_{idx}"
            if "." not in raw_name:
                raw_name += _MIME_EXT_FALLBACK.get(ctype) or mimetypes.guess_extension(ctype) or ".html"

            dst = cache_dir / f"{idx}_{raw_name}"
            dst.write_bytes(data)
            downloaded.append(dst)
            logger.info(f"✔ fetched {link} → {dst}")

        except Exception as exc:  # noqa: BLE001
            logger.error(f"⚠  could not fetch {link}: {exc}")

    return downloaded


def _scrape_urls(
        seeds: List[str],
        cache_root: Path,
        *,
        suffixes: List[str],
        exclude_suf: List[str],
        max_depth: int = 2,
        same_host_only: bool = True,
) -> List[Path]:
    """
    Rastreo BFS con filtrado estricto usando listas de extensiones
    “well-known” (WKE) + reglas -s / -S.

    ▸ Si hay -s / -S:
        · Una URL con WKE no listada por -s se descarta.
        · Una URL con WKE en -S (y no en -s) se descarta.
    ▸ Extensiones no WKE:
        · Se aceptan sólo si están en -s; de lo contrario se
          descargan para inspección y, si son texto, se tratan
          como .html (o el fallback MIME).
    ▸ Binarios se eliminan tras la descarga si se colaron.
    """
    import urllib.request, urllib.parse, mimetypes, html, re
    from collections import deque

    # ────────────────────────── Catálogo WKE ──────────────────────────
    # Texto / marcado / código
    TEXT_EXT = {
        ".html", ".htm", ".xhtml",
        ".md", ".markdown",
        ".txt", ".text",
        ".css", ".scss", ".less",
        ".js", ".mjs", ".ts", ".tsx", ".jsx",
        ".json", ".jsonc", ".yaml", ".yml",
        ".xml", ".svg",
        ".csv", ".tsv",
        ".py", ".rb", ".php", ".pl", ".pm",
        ".go", ".rs", ".java", ".c", ".cpp", ".cc", ".h", ".hpp",
        ".sh", ".bash", ".zsh", ".ps1",
        ".r", ".lua",
    }

    # Binarios “web-ish” que solemos querer descartar salvo que el
    # usuario los pida explícitamente con -s
    BINARY_EXT = {
        # imágenes
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".avif",
        # vídeo
        ".mp4", ".m4v", ".mov", ".webm", ".ogv", ".flv",
        # audio
        ".mp3", ".ogg", ".oga", ".wav", ".flac",
        # fuentes
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        # documentos
        ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
        # compresión / binarios genéricos
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    }

    WELL_KNOWN_EXT = TEXT_EXT | BINARY_EXT

    # Fallback cuando la URL carece de extensión válida
    _EXT_FALLBACK = {
        "text/html": ".html",
        "application/json": ".json",
        "application/javascript": ".js",
        "text/css": ".css",
        "text/plain": ".txt",
        "text/xml": ".xml",
    }

    include_set = {s if s.startswith(".") else f".{s}" for s in suffixes}
    exclude_set = {s if s.startswith(".") else f".{s}" for s in exclude_suf} - include_set

    cache_dir = cache_root / ".ghconcat_urlcache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    href_re = re.compile(r'href=["\']?([^"\' >]+)', re.I)
    ext_re = re.compile(r"\.[A-Za-z0-9_-]{1,8}$")
    ua_hdr = {"User-Agent": "ghconcat/2.0 (+https://gaheos.com)"}

    # ─────────────── utilidades ───────────────
    def _extract_ext(url: str) -> str:
        m = ext_re.search(urllib.parse.urlparse(url).path)
        return m.group(0).lower() if m else ""

    def _is_binary_mime(ctype: str) -> bool:
        if ctype.startswith("text/") or ctype.endswith(("+xml", "+json", "+html")):
            return False
        if ctype in ("application/json", "application/javascript", "application/xml"):
            return False
        return True

    def _skip_pre_download(ext: str) -> bool:
        """Decide si una URL debe descartarse sin descargar."""
        # 1) Extensión reconocida
        if ext in WELL_KNOWN_EXT:
            if include_set and ext not in include_set:
                return True  # WKE no pedida
            if ext in exclude_set:
                return True  # WKE excluida
            return False  # pasa filtros
        # 2) Extensión rara / inexistente
        if ext in exclude_set:
            return True
        if include_set and ext not in include_set:
            # no pedida explícitamente, pero permitimos descargar
            # para inspección (quizá sea html sin ext)
            return False
        return False  # se descarga para inspección

    def _download(url: str, idx: int, depth: int):
        try:
            req = urllib.request.Request(url, headers=ua_hdr)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip()

            name = Path(urllib.parse.urlparse(url).path).name or f"remote_{idx}"
            ext = _extract_ext(name)

            # Ajustar nombre si no termina en una extensión coherente
            if not ext or ext not in WELL_KNOWN_EXT:
                ext = include_set.intersection({ext}).pop() if ext in include_set else ""
                if not ext:
                    ext = _EXT_FALLBACK.get(ctype) or ".html"
                if not name.lower().endswith(ext):
                    name += ext

            dst = cache_dir / f"scr_{idx}_{name}"
            dst.write_bytes(data)
            logger.info(f"✔ scraped {url} (d={depth}) → {dst}")
            return dst, ctype, data
        except Exception as exc:  # noqa: BLE001
            logger.error(f"⚠  could not scrape {url}: {exc}")
            return None

    # ─────────────── BFS ───────────────
    visited: set[str] = set()
    queue = deque([(u, 0) for u in seeds])
    out_paths: List[Path] = []

    while queue:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        ext = _extract_ext(url)
        if _skip_pre_download(ext):
            continue

        dl = _download(url, len(visited), depth)
        if dl is None:
            continue
        dst, ctype, body = dl

        # Verificación binaria posterior (p.ej. ext rara + MIME binario)
        if _is_binary_mime(ctype) and dst.suffix.lower() not in include_set:
            try:
                dst.unlink(missing_ok=True)
            except Exception:
                pass
            continue

        out_paths.append(dst)

        # Expandir enlaces HTML
        if ctype.startswith("text/html") and depth < max_depth:
            try:
                html_txt = body.decode("utf-8", "ignore")
                for link in href_re.findall(html_txt):
                    abs_url = urllib.parse.urljoin(url, html.unescape(link))
                    if same_host_only and urllib.parse.urlparse(abs_url)[:2] != urllib.parse.urlparse(url)[:2]:
                        continue
                    if abs_url in visited:
                        continue
                    if _skip_pre_download(_extract_ext(abs_url)):
                        continue
                    queue.append((abs_url, depth + 1))
            except Exception:
                pass

    return out_paths


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
    env_map: Dict[str, str] = {}
    for itm in items or []:
        if "=" not in itm:
            _fatal(f"--env expects VAR=VAL (got '{itm}')")
        key, val = itm.split("=", 1)
        env_map[key] = val
    return env_map


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
    Recursive executor. Returns *(vars, final_output)* for *node*.

    Workdir/workspace semantics (as requested):
    - Level 0:
        · -w is resolved against the process CWD (Path.cwd()).
        · -W is resolved against the computed -w (workdir).
        · If -w is omitted, it defaults to CWD.
        · If only -W is provided, it is still resolved against -w (thus CWD).
    - Children:
        · If a child DOES NOT provide -w, it inherits the parent's root *as-is*
          (no re-resolution). This prevents duplicate “…/dir/dir”.
        · If a child provides -w, it is resolved against the parent's root.
        · If a child provides -W, it is resolved against the parent's workspace
          when available; otherwise it falls back to the current root.
        · If a child omits -W, it inherits the parent's workspace unchanged.
    """
    inherited_vars = inherited_vars or {}
    tokens = _expand_tokens(node.tokens, inherited_env=inherited_vars)

    ns_self = _build_parser().parse_args(tokens)
    _post_parse(ns_self)

    # Effective namespace (values + flags); still no path resolution here.
    ns_effective = _merge_ns(ns_parent, ns_self) if ns_parent else ns_self

    # ── Root init at level 0 ──────────────────────────────────────────────
    if level == 0:
        gh_dump = []
        _SEEN_FILES.clear()

    # ── Resolve workdir (root) with explicit-vs-inherited semantics ───────
    if ns_parent is None:
        # Level 0: -w against CWD (default '.')
        base_for_root = Path.cwd()
        root = _resolve_path(base_for_root, ns_effective.workdir or ".")
    else:
        # Child:
        # If this context explicitly set -w, resolve it against the parent's root.
        # Otherwise keep using the parent's root *as-is* (no re-resolution).
        if ns_self.workdir not in (None, ""):
            base_for_root = parent_root or Path.cwd()
            root = _resolve_path(base_for_root, ns_self.workdir)
        else:
            root = parent_root or Path.cwd()

    # ── Resolve workspace with the requested hierarchy ────────────────────
    if ns_parent is None:
        # Level 0:
        if ns_self.workspace not in (None, ""):
            # -W relative to computed root (-w)
            workspace = _resolve_path(root, ns_self.workspace)
        else:
            workspace = root
    else:
        # Child:
        if ns_self.workspace not in (None, ""):
            # -W relative to parent workspace when available; otherwise to root
            base_ws = parent_workspace or root
            workspace = _resolve_path(base_ws, ns_self.workspace)
        else:
            # Inherit parent's workspace unchanged; or fallback to current root
            workspace = parent_workspace or root

    _WORKSPACES_SEEN.add(workspace)
    ns_effective.workspace = str(workspace)  # Freeze as absolute for this scope

    if not root.exists():
        _fatal(f"--workdir {root} not found")
    if not workspace.exists():
        _fatal(f"--workspace {workspace} not found")

    # ── Variable scopes ───────────────────────────────────────────────────
    global_env_map = _parse_env_items(ns_effective.global_env)
    local_env_map = _parse_env_items(ns_effective.env_vars)

    inherited_for_children = {**inherited_vars, **global_env_map}
    vars_local = {**inherited_for_children, **local_env_map}
    ctx_name = node.name

    # ── Child-template (-T) propagation model ─────────────────────────────
    parent_child_tpl = getattr(ns_parent, "child_template", None) if ns_parent else None
    local_child_tpl = getattr(ns_self, "child_template", None)
    child_tpl_for_descendants = (
        local_child_tpl if local_child_tpl not in (None, "") else parent_child_tpl
    )
    ns_effective.child_template = child_tpl_for_descendants  # what children will see

    # ── Raw concatenation (local + remote sources) ────────────────────────
    dump_raw = ""
    if (
        ns_effective.add_path
        or ns_effective.git_path
        or ns_effective.urls
        or ns_effective.url_scrape
    ):
        suffixes = _split_list(ns_effective.suffix)
        exclude_suf = _split_list(ns_effective.exclude_suf)

        # 1) Local filesystem
        local_files: List[Path] = []
        if ns_effective.add_path:
            local_files = _gather_files(
                add_path=[
                    Path(p) if Path(p).is_absolute() else (root / p).resolve()
                    for p in ns_effective.add_path
                ],
                exclude_dirs=[
                    Path(p) if Path(p).is_absolute() else (root / p).resolve()
                    for p in ns_effective.exclude_path or []
                ],
                suffixes=suffixes,
                exclude_suf=exclude_suf,
            )

        # 1-bis) Git repositories (-g / -G)
        git_files: List[Path] = _collect_git_files(
            ns_effective.git_path,
            ns_effective.git_exclude,
            workspace,
            suffixes,
            exclude_suf,
        )

        # 2) Point downloads (-f/--url)
        remote_files: List[Path] = []
        if ns_effective.urls:
            remote_files = _fetch_urls(ns_effective.urls, workspace)

        # 3) Recursive scraping (-F/--url-scrape)
        scraped_files: List[Path] = []
        if ns_effective.url_scrape:
            max_depth = (
                2 if ns_effective.url_scrape_depth is None
                else ns_effective.url_scrape_depth
            )
            scraped_files = _scrape_urls(
                ns_effective.url_scrape,
                workspace,
                suffixes=suffixes,
                exclude_suf=exclude_suf,
                max_depth=max_depth,
                same_host_only=not ns_effective.disable_url_domain_only,
            )

        files = [*local_files, *remote_files, *scraped_files, *git_files]

        if files:
            wrapped: Optional[List[Tuple[str, str]]] = [] if ns_effective.wrap_lang else None
            dump_raw = _concat_files(
                files, ns_effective, header_root=root, wrapped=wrapped,
            )

            if ns_effective.wrap_lang and wrapped:
                fenced: List[str] = []
                for hp, body in wrapped:
                    hdr = "" if ns_effective.skip_headers else f"{HEADER_DELIM}{hp} {HEADER_DELIM}\n"
                    fenced.append(
                        f"{hdr}```{ns_effective.wrap_lang or Path(hp).suffix.lstrip('.')}\n"
                        f"{body}\n```\n"
                    )
                dump_raw = "".join(fenced)

    # ── Expose raw to variables ───────────────────────────────────────────
    if ctx_name:
        vars_local[f"_r_{ctx_name}"] = dump_raw
        vars_local[ctx_name] = dump_raw
    if gh_dump is not None:
        gh_dump.append(dump_raw)

    _refresh_env_values(vars_local)

    # ── Recurse into children ─────────────────────────────────────────────
    for child in node.children:
        child_vars, _ = _execute_node(
            child,
            ns_effective,
            level=level + 1,
            parent_root=root,
            parent_workspace=workspace,
            inherited_vars=inherited_for_children,
            gh_dump=gh_dump,
        )
        vars_local.update(child_vars)
        inherited_for_children.update(child_vars)

        nxt = child_vars.get("__GH_NEXT_CHILD_TEMPLATE__", None)
        if nxt is not None:
            ns_effective.child_template = (nxt or None)

    _refresh_env_values(vars_local)

    # ── Templating (local -t, else parent -T) ─────────────────────────────
    rendered = dump_raw
    chosen_tpl = ns_effective.template or parent_child_tpl
    if chosen_tpl:
        tpl_path = _resolve_path(workspace, chosen_tpl)
        if not tpl_path.exists():
            _fatal(f"template {tpl_path} not found")
        rendered = _interpolate(
            tpl_path.read_text(encoding="utf-8"),
            {**vars_local, "ghconcat_dump": "".join(gh_dump or [])},
        )

    if ctx_name:
        vars_local[f"_t_{ctx_name}"] = rendered
        vars_local[ctx_name] = rendered

    _refresh_env_values(vars_local)

    # ── AI gateway (optional) ─────────────────────────────────────────────
    final_out = rendered
    out_path: Optional[Path] = None
    if ns_effective.output and ns_effective.output.lower() != TOK_NONE:
        out_path = _resolve_path(workspace, ns_effective.output)

    if ns_effective.ai:
        if out_path is None:
            tf = tempfile.NamedTemporaryFile(
                delete=False, dir=workspace, suffix=".ai.txt"
            )
            tf.close()
            out_path = Path(tf.name)

        sys_prompt = ""
        if (ns_effective.ai_system_prompt
                and ns_effective.ai_system_prompt.lower() != TOK_NONE):
            spath = _resolve_path(workspace, ns_effective.ai_system_prompt)
            if not spath.exists():
                _fatal(f"system prompt {spath} not found")
            sys_prompt = _interpolate(spath.read_text(encoding="utf-8"), vars_local)

        seeds = None
        if (ns_effective.ai_seeds
                and ns_effective.ai_seeds.lower() != TOK_NONE):
            seeds = _resolve_path(workspace, ns_effective.ai_seeds)

        (_call_openai if "ghconcat" not in sys.modules else
         getattr(sys.modules["ghconcat"], "_call_openai"))(
            rendered,
            out_path,
            model=ns_effective.ai_model,
            system_prompt=sys_prompt,
            temperature=ns_effective.ai_temperature,
            top_p=ns_effective.ai_top_p,
            presence_pen=ns_effective.ai_presence_penalty,
            freq_pen=ns_effective.ai_frequency_penalty,
            seeds_path=seeds,
        )
        final_out = out_path.read_text(encoding="utf-8")

    if ctx_name:
        vars_local[f"_ia_{ctx_name}"] = final_out
        vars_local[ctx_name] = final_out

    _refresh_env_values(vars_local)

    # ── Write output (if -o and no AI) ────────────────────────────────────
    if out_path and not ns_effective.ai:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(final_out, encoding="utf-8")
        logger.info(f"✔ Output written → {out_path}")

    # ── STDOUT forwarding rules ───────────────────────────────────────────
    force_stdout = getattr(ns_effective, "to_stdout", False)
    auto_root_stdout = (level == 0 and ns_effective.output in (None, TOK_NONE))
    if force_stdout or (auto_root_stdout and not force_stdout):
        if not sys.stdout.isatty():
            sys.stdout.write(final_out)
        else:
            print(final_out, end="")

    # ── Root dump fallback ────────────────────────────────────────────────
    if level == 0 and final_out == "" and gh_dump:
        final_out = "".join(gh_dump)
    if level == 0 and gh_dump is not None:
        vars_local["ghconcat_dump"] = "".join(gh_dump)

    # Expose -T for subsequent siblings at the same level
    vars_local["__GH_NEXT_CHILD_TEMPLATE__"] = child_tpl_for_descendants or ""

    return vars_local, final_out


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
    Borra todos los «.ghconcat_*cache» vistos durante la ejecución
    (git + URL scraper) salvo que la sesión pidiera conservarlos.
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

        # ── split by “-x” -------------------------------------------------
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
                # Normaliza los tokens acumulados antes de guardar
                units.append((fpath, _inject_positional_add_paths(cli_remainder)))
                cli_remainder = []
            else:
                cli_remainder.append(tok)

        # Cola final (sin -x explícito)
        if not units:
            units.append((None, _inject_positional_add_paths(cli_remainder)))
        elif cli_remainder:
            last_path, last_cli = units[-1]
            units[-1] = (last_path, last_cli + _inject_positional_add_paths(cli_remainder))

        # ── execute each unit --------------------------------------------
        outputs: List[str] = []
        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()  # dedup scope per unit

            if directive_path:
                root = _parse_directive_file(directive_path)
                root.tokens.extend(extra_cli)
            else:
                root = DirNode()
                root.tokens.extend(extra_cli)

            # Self-upgrade shortcut
            if "--upgrade" in root.tokens:
                (_perform_upgrade if "ghconcat" not in sys.modules
                 else getattr(sys.modules["ghconcat"], "_perform_upgrade"))()

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if "--preserve-cache" not in argv:
            _purge_caches()

        return "".join(outputs)


# ────────────────────────────  CLI main()  ──────────────────────────────────
def main() -> None:  # pragma: no cover
    """
    CLI dispatcher usado por el ejecutable real «ghconcat».

    El manejo de STDOUT se delega ahora a _execute_node(), por lo que
    aquí ya NO se emite automáticamente el resultado.
    """
    global _CLI_MODE
    _CLI_MODE = True
    try:
        GhConcat.run(sys.argv[1:])
    except KeyboardInterrupt:
        _fatal("Interrupted by user.", 130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        if _debug_enabled():
            raise
        _fatal(f"Unexpected error: {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()
