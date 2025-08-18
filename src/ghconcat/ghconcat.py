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
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import logging
import ssl

try:
    from lxml import etree as _ET  # type: ignore

    _ET_PARSER = _ET.HTMLParser(recover=True)
except ModuleNotFoundError:  # lxml no instalado
    try:
        import xml.etree.ElementTree as _ET  # type: ignore

        _ET_PARSER = None  # ElementTree no necesita parser
    except ModuleNotFoundError:
        _ET = None  # sin ningún etree

from .walker import WalkerAppender
from .url_fetcher import UrlFetcher
from .pdf_reader import PdfTextExtractor
from .excel_reader import ExcelTsvExporter
from .readers import get_global_reader_registry
from .html_reader import HtmlToTextReader
from .git_repository import GitRepositoryManager
from .textops import TextTransformer
from .envctx import EnvContext
from .directives import DirNode, parse_directive_file as _parse_directive_file
from .flags import VALUE_FLAGS as _VALUE_FLAGS
from .tokenize import inject_positional_add_paths  # NEW
from .execution import ExecutionEngine, PathResolver, FileDiscovery, Renderer, AIProcessor, make_default_walker

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ghconcat")

# ───────────────────────────────  Constants  ────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_CLI_MODE: bool = False
HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

_LINE1_RE: re.Pattern[str] = re.compile(r"^\s*#\s*line\s*1\d*\s*$")
_WORKSPACES_SEEN: set[Path] = set()

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
    Build an SSL context for *url* honoring the env var:

        GHCONCAT_INSECURE_TLS=1  → desactiva la verificación de certificados.

    Si no está activada o la URL no es HTTPS, devuelve None (contexto por defecto).
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

    NEW: delegated to :class:`GitRepositoryManager`.
    """
    return GitRepositoryManager(workspace, logger=logger, clones_cache=_GIT_CLONES).git_cache_root()


def _parse_git_spec(spec: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse a `-g / -G` SPEC and return **(repo_url, branch, sub_path)**.

    NEW: delegated to :class:`GitRepositoryManager.parse_spec`.
    """
    return GitRepositoryManager.parse_spec(spec)


def _clone_git_repo(repo_url: str, branch: Optional[str], cache_root: Path) -> Path:
    """
    Clone *repo_url* (shallow) into *cache_root* unless an identical copy
    already exists.  Returns the path to the checked‑out work‑tree.

    NEW: backwards-compatible wrapper delegating to :class:`GitRepositoryManager`.
    Note: *cache_root* is accepted for signature compatibility; the manager derives
    the real workspace cache directory. If *cache_root* already points to
    ``<workspace>/.ghconcat_gitcache``, the workspace is inferred as its parent.
    """
    workspace = cache_root.parent if cache_root.name == ".ghconcat_gitcache" else cache_root
    mgr = GitRepositoryManager(workspace, logger=logger, clones_cache=_GIT_CLONES)
    try:
        return mgr.clone_repo(repo_url, branch)
    except Exception as exc:  # noqa: BLE001
        _fatal(f"could not clone {repo_url}: {exc}")
        raise


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
    • El directorio «.ghconcat_gitcache» *no* se considera “oculto”.

    NEW: implementation delegated to :class:`GitRepositoryManager` (1:1 behavior).
    """
    if not git_specs:
        return []
    mgr = GitRepositoryManager(workspace, logger=logger, clones_cache=_GIT_CLONES)
    try:
        return mgr.collect_files(git_specs, git_exclude_specs or [], suffixes, exclude_suf)
    except Exception as exc:  # noqa: BLE001
        logger.error("⚠  git collection failed: %s", exc)
        return []


def _parse_replace_spec(spec: str) -> tuple[re.Pattern[str], str, bool] | None:
    """
    Parse a *-y / -Y* SPEC and return a tuple (regex, replacement, global_flag).

    This thin wrapper preserves the original public function while delegating
    to the library-level TextTransformer. Behavioral compatibility is 1:1 with
    the legacy implementation.
    """
    return _TEXT_TRANSFORMER.parse_replace_spec(spec)


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


# ───────────────────────────  Lectura universal de archivos  ────────────────────────────
def _extract_pdf_text(
        pdf_path: Path,
        *,
        ocr_if_empty: bool = True,
        dpi: int = 300,
) -> str:
    """
    Return the full plaintext from *pdf_path*.

    This thin wrapper delegates to :class:`PdfTextExtractor` to keep the
    behavior identical while exposing a clean library class.
    """
    return PdfTextExtractor(logger=logger, ocr_if_empty=ocr_if_empty, dpi=dpi).extract_text(pdf_path)


def _extract_excel_tsv(xls_path: Path) -> str:
    """
    Return a **tab-separated** textual dump of *every* sheet in *xls_path*.

    The implementation is delegated to :class:`ExcelTsvExporter` to keep
    behavior 1:1 with the legacy function while providing an OOP entry point.
    """
    return ExcelTsvExporter(logger=logger).export_tsv(xls_path)


def _read_file_as_lines(fp: Path) -> list[str]:
    """
    Return *fp* as a list of **text lines**:

    • PDF   → `_extract_pdf_text`
    • Excel → `_extract_excel_tsv` (all sheets, TSV)
    • Other → via registry (UTF-8 reader by default)
    • Binary/undecodable files are skipped (empty list, logged)
    """
    return get_global_reader_registry(logger).read_lines(fp)


def _strip_none(tokens: List[str]) -> List[str]:
    """
    Remove *both* a flag and its value when the value is literally “none”.

    Thin wrapper delegating to :class:`EnvContext` to keep the original
    semantics while centralizing the logic in the env engine.
    """
    return _ENV_CONTEXT.strip_none(tokens, value_flags=_VALUE_FLAGS, none_value=TOK_NONE)


def _substitute_env(tokens: List[str], env_map: Dict[str, str]) -> List[str]:
    """
    Replace every «$VAR» occurrence with its value from *env_map*.

    Values immediately following -e/--env and -E/--global-env remain
    literal, matching legacy behavior. Implementation delegated to
    :class:`EnvContext`.
    """
    return _ENV_CONTEXT.substitute_in_tokens(tokens, env_map)


def _collect_env_from_tokens(tokens: Sequence[str]) -> Dict[str, str]:
    """
    Scan *tokens* and gather every definition that follows “‑e/‑E”.

    Delegates to :class:`EnvContext`, using the local `_fatal` for strict
    error handling (exit on malformed assignments), preserving previous
    CLI behavior.
    """
    return _ENV_CONTEXT.collect_from_tokens(tokens, on_error=lambda m: _fatal(m))


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


def _refresh_env_values(env_map: Dict[str, str]) -> None:
    """
    Re-evaluate *env_map* until no “$VAR” references remain.

    Delegates to :class:`EnvContext`. This method updates the mapping
    in-place and remains a no-op on already-expanded maps.
    """
    _ENV_CONTEXT.refresh_values(env_map)


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
    replace/preserve engine.
    """
    wa = WalkerAppender(
        read_file_as_lines=_read_file_as_lines,
        html_to_text=_html_to_text,  # kept for constructor compatibility (unused)
        apply_replacements=_apply_replacements,
        slice_lines=_slice,
        clean_lines=_clean,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
        logger=logger,
    )

    # NEW: enable HtmlToTextReader via the registry if -K/--textify-html is set.
    # We scope this override to the current concatenation only and then restore.
    reg = get_global_reader_registry(logger)
    restore_html_reader = None
    if getattr(ns, "strip_html", False):
        try:
            restore_html_reader = reg.for_suffix(".html")
            reg.register([".html"], HtmlToTextReader(logger=logger))
        except Exception:  # noqa: BLE001
            restore_html_reader = None  # fail-open, do not block execution

    try:
        return wa.concat_files(files, ns, header_root=header_root, wrapped=wrapped)
    finally:
        if restore_html_reader is not None:
            try:
                reg.register([".html"], restore_html_reader)
            except Exception:  # noqa: BLE001
                pass


def _gather_files(
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
) -> List[Path]:
    """
    Walk *add_path* and return every file that matches inclusion / exclusion
    rules. Explicit files always win.

    Esta versión delega **siempre** en `WalkerAppender` (OOP).
    """
    return WalkerAppender(
        read_file_as_lines=_read_file_as_lines,
        html_to_text=_html_to_text,
        apply_replacements=_apply_replacements,
        slice_lines=_slice,
        clean_lines=_clean,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
        logger=logger,
    ).gather_files(add_path, exclude_dirs, suffixes, exclude_suf)


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
        from .ai_client import OpenAIClient
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


def _fetch_urls(urls: List[str], cache_root: Path) -> List[Path]:
    """
    Download every *URL* into a temporary cache directory under *cache_root*
    and return a list of `Path` objects pointing to the downloaded files.

    This is now delegated to :class:`UrlFetcher` to keep behavior identical
    while providing a clean library interface.
    """
    return UrlFetcher(
        cache_root,
        logger=logger,
        ssl_ctx_provider=_ssl_ctx_for,
    ).fetch(urls)


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
    Depth-limited BFS crawler honoring include/exclude suffix filters.

    The legacy semantics are preserved and the implementation is delegated
    to :class:`UrlFetcher`, ensuring 1:1 behavior and test compatibility.
    """
    return UrlFetcher(
        cache_root,
        logger=logger,
        ssl_ctx_provider=_ssl_ctx_for,
    ).scrape(
        seeds,
        suffixes=suffixes,
        exclude_suf=exclude_suf,
        max_depth=max_depth,
        same_host_only=same_host_only,
    )


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
    Backwards-compatible wrapper delegating to the new ExecutionEngine.

    The signature and behavior remain identical. This thin wrapper wires the
    default collaborators to preserve the exact semantics verified by tests.
    """
    # Build default wiring on each call to avoid cross-run state leaks
    env = _ENV_CONTEXT  # reuse existing singleton with same behavior

    # Discovery façade: reuse existing helpers for full compatibility
    def _mk_discovery() -> FileDiscovery:
        return FileDiscovery(
            gather_files=_gather_files,
            collect_git_files=_collect_git_files,
            fetch_urls=_fetch_urls,
            scrape_urls_ext=lambda seeds, cache_root, suffixes, exclude_suf, max_depth, same_host_only: _scrape_urls(
                seeds,
                cache_root,
                suffixes=suffixes,
                exclude_suf=exclude_suf,
                max_depth=max_depth,
                same_host_only=same_host_only,
            ),
        )

    renderer = Renderer(interpolate=_interpolate, header_delim=HEADER_DELIM, logger=logger)

    ai = AIProcessor(
        call_openai=(
            _call_openai if "ghconcat" not in sys.modules else getattr(sys.modules["ghconcat"], "_call_openai")),
        logger=logger,
    )

    engine = ExecutionEngine(
        parser_factory=_build_parser,
        post_parse=_post_parse,
        env_context=env,
        path_resolver=PathResolver(),
        file_discovery=_mk_discovery(),
        renderer=renderer,
        ai_processor=ai,
        walker_factory=lambda seen: make_default_walker(HEADER_DELIM, seen, logger),
        logger=logger,
    )

    return engine.execute(
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
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute ghconcat over *argv* and return the concatenation result.
        """
        global _SEEN_FILES
        _SEEN_FILES = set()
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
                # UPDATED: use centralized inject_positional_add_paths
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
        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()

            if directive_path:
                root = _parse_directive_file(directive_path)
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
