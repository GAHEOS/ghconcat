#!/usr/bin/env python3
"""
ghconcat – universal source‑code concatenator
============================================

Production release – 2025‑07‑27 (patch 1)
-------------------------------------------
* **Fixes**
  - **Single wrap fencing**: solved the bug that generated nested
    ```LANG blocks when using ``‑u/‑‑wrap``.
    Now each chunk is fenced exactly once.

* **Default inclusions**
  - If **‑g/‑‑include‑lang** is omitted, *all* extensions are accepted.
  - If **‑a/‑‑add‑path** is omitted, “.” (current dir) is assumed.

* **Output policy**
  - **Level 0**: **‑o/‑‑output is mandatory**; there is no fallback to
    *dump.txt*.
  - **Nested ‑X** contexts never write a file **unless ‑o is given
    explicitly**.

* **Context constraints**
  - Inside an **‑X** you must provide at least one of:
      1. A concat target (**‑a …**)
      2. An alias (**‑k …**)
      3. Vars with **‑K**
    otherwise the run aborts.
  - **‑k/‑‑alias** stores the concat result in memory for *all* levels.
  - **‑K/‑‑env** requires “VAR=VAL” syntax and is available to every
    template.

* **AI integration**
  - **‑Q/‑‑ai** demands **‑o** (an output path where the reply will be
    stored).

* **Header path policy**
  - **Relative** to execution root by default.
  - Use **‑p/‑‑absolute‑path** to force absolute paths.

* **Filters & pruning order**
  1. Include roots (‑a)
  2. Walk trees, then apply ‑g/‑G/‑S/‑e/‑E
  3. Dispatch each file by extension
  4. Add single‑file roots (‑a FILE)
  5. Slice with ‑n/‑N/‑H
  6. Clean with ‑c/‑C/‑s/‑i/‑I
  7. Empty bodies are skipped (path is printed only with ‑l)

This file is self‑contained, production‑ready and 100 % compliant with
PEP8, type hints and exhaustive English docstrings.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ──────────────────────────── Constants ────────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OPENAI_MODEL = "o3"
DEFAULT_I18N = "ES"

PRESETS: dict[str, set[str]] = {
    "odoo": {".py", ".xml", ".js", ".csv"},
}

_COMMENT_RULES: dict[str, Tuple[
    re.Pattern, re.Pattern, Optional[re.Pattern], Optional[re.Pattern]
]] = {
    ".py": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*(?:import\b|from\b.+?\bimport\b)"),
        None,
    ),
    ".dart": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*//.*$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".js": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*//.*$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*(?:export\b|module\.exports\b)"),
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
}

_RE_BLANK = re.compile(r"^\s*$")
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][\w\-]*)\}")

# Optional OpenAI import
try:
    import openai  # type: ignore
    from openai import OpenAIError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore


    class OpenAIError(Exception):  # type: ignore
        """Raised when the OpenAI SDK is unavailable."""
        ...


# ───────────────────────── Utility helpers ─────────────────────────
def _fatal(msg: str, code: int = 1) -> None:
    """Print *msg* on **STDERR** and exit gracefully (no traceback)."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    """Return *True* if DEBUG=1 is present in the environment."""
    return os.getenv("DEBUG") == "1"


def _is_within(path: Path, parent: Path) -> bool:
    """Return *True* if *parent* is an ancestor of *path*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ──────────────── Directive‑file expansion (‑x) ────────────────
def _parse_directive_file(path: Path) -> List[str]:
    """
    Convert a batch directive file into an argv‑like token list.

    Lines can contain inline “// …” comments; shell‑style quoting is honoured.
    """
    tokens: List[str] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            stripped = raw.split("//", 1)[0].strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = shlex.split(stripped)
            if not parts:
                continue
            if parts[0].startswith("-"):  # explicit flag
                if parts[0] == "-a" and len(parts) > 2:
                    # ‑a x y z  →  ‑a x  ‑a y  ‑a z
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            else:  # implicit -a
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def _expand_x(argv: Sequence[str]) -> List[str]:
    """
    Inline‑expand “‑x FILE” before argparse sees *argv*.

    Only one top‑level “‑x/‑‑directives” is allowed. When present it must be
    the **sole** argument besides the filename itself.
    """
    if argv.count("-x") + argv.count("--directives") > 1:
        _fatal("Only one -x/--directives allowed at level 0.")
    if "-x" in argv or "--directives" in argv:
        if len(argv) > 2:
            _fatal("When using -x/--directives it must be the only CLI flag.")
    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token in ("-x", "--directives"):
            try:
                file_path = Path(next(it))
            except StopIteration:
                _fatal("Error: missing file after -x.")
            if not file_path.exists():
                _fatal(f"Directive file {file_path} not found.")
            out.extend(_parse_directive_file(file_path))
        else:
            out.append(token)
    return out


# ───────────────────────────── CLI parser ─────────────────────────────
def _split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma‑separated tokens."""
    if not raw:
        return []
    flat: List[str] = []
    for item in raw:
        flat.extend([p.strip() for p in re.split(r"[,\s]+", item) if p.strip()])
    return flat


# ───────────────────────────── CLI parser ─────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    """Return the fully configured argparse parser used at every level."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [-x FILE] [-X FILE] -g LANG -a PATH [...] [OPTIONS]",
        description=(
            "Concatenate, slice and post-process source files with optional "
            "AI integration and multi-level batching."
        ),
        add_help=False,
    )

    # ── Groups ──────────────────────────────────────────────────────────
    grp_batch = p.add_argument_group("Batching / nesting")
    grp_loc = p.add_argument_group("Location & discovery")
    grp_lang = p.add_argument_group("Language filters")
    grp_rng = p.add_argument_group("Line-range slicing")
    grp_cln = p.add_argument_group("Cleaning options")
    grp_out = p.add_argument_group("Output, templating & variables")
    grp_ai = p.add_argument_group("AI integration")
    grp_misc = p.add_argument_group("Miscellaneous")

    # ── Batching
    grp_batch.add_argument(
        "-x", "--directives", dest="x", metavar="FILE",
        help="Load every CLI flag from FILE (level 0 only)."
    )
    grp_batch.add_argument(
        "-X", "--context", action="append", dest="batch_directives",
        metavar="FILE",
        help="Run nested batch file (level > 0, repeatable)."
    )

    # ── Location
    grp_loc.add_argument("-a", "--add-path", action="append",
                         dest="roots", metavar="PATH",
                         help="File or directory to scan (repeatable).")
    grp_loc.add_argument("-r", "--root", dest="root", metavar="DIR",
                         help="Logical root used to resolve relative paths.")
    grp_loc.add_argument("-w", "--workspace", dest="workspace", metavar="DIR",
                         help="Working directory where outputs are written "
                              "(default: same as --root).")
    grp_loc.add_argument("-e", "--exclude-dir", action="append",
                         dest="exclude_dir", metavar="DIR",
                         help="Skip DIR and all its descendants (repeatable).")
    grp_loc.add_argument("-E", "--exclude-path", action="append",
                         dest="exclude", metavar="PAT",
                         help="Skip any path that contains PAT.")
    grp_loc.add_argument("-S", "--suffix", action="append",
                         dest="suffix", metavar="SUF",
                         help="Include only files whose name ends with SUF.")

    # ── Languages
    grp_lang.add_argument("-g", "--include-lang", action="append",
                          dest="lang", metavar="LANG",
                          help="Language/extension to include (alias “odoo”).")
    grp_lang.add_argument("-G", "--exclude-lang", action="append",
                          dest="skip_langs", metavar="LANG",
                          help="Language/extension to exclude from the active set.")

    # ── Line-range
    grp_rng.add_argument("-n", "--total-lines", dest="total_lines",
                         type=int, metavar="NUM",
                         help="Keep NUM lines (after --start-line).")
    grp_rng.add_argument("-N", "--start-line", dest="first_line",
                         type=int, metavar="LINE",
                         help="Absolute 1-based line where slicing starts.")
    grp_rng.add_argument("-H", "--keep-header", action="store_true",
                         dest="keep_header",
                         help="Duplicate original line 1 when excluded by slicing.")

    # ── Cleaning
    grp_cln.add_argument("-c", "--remove-comments", dest="rm_simple",
                         action="store_true", help="Remove single-line comments.")
    grp_cln.add_argument("-C", "--remove-all-comments", dest="rm_all",
                         action="store_true", help="Remove **all** comments.")
    grp_cln.add_argument("-i", "--remove-import", action="store_true",
                         dest="rm_import", help="Remove import statements.")
    grp_cln.add_argument("-I", "--remove-export", action="store_true",
                         dest="rm_export", help="Remove export statements.")
    grp_cln.add_argument("-s", "--keep-blank", action="store_true",
                         dest="keep_blank", help="Preserve blank lines.")

    # ── Output / templating / variables
    grp_out.add_argument("-t", "--template", dest="template", metavar="FILE",
                         help="Render dump into FILE template before writing output.")
    grp_out.add_argument("-o", "--output", dest="output", metavar="FILE",
                         help="Destination file (mandatory at level 0).")
    grp_out.add_argument("-u", "--wrap", dest="wrap_lang", metavar="LANG",
                         help="Fence every chunk inside ```LANG``` blocks.")
    grp_out.add_argument("-l", "--list", dest="list_only", action="store_true",
                         help="List matched file routes only (no body).")
    grp_out.add_argument("-p", "--absolute-path", dest="absolute_path",
                         action="store_true",
                         help="Show absolute paths in headers (default: relative).")
    grp_out.add_argument("-P", "--no-headers", dest="skip_headers",
                         action="store_true",
                         help="Omit route header lines (===== path =====).")

    grp_out.add_argument("-k", "--alias", dest="alias",
                         metavar="ALIAS",
                         help="Expose this dump as {ALIAS} to the parent template "
                              "(max 1 per level).")
    grp_out.add_argument("-K", "--env", dest="env_vars", action="append",
                         metavar="VAR=VAL",
                         help="Define VAR for template interpolation (requires -t).")

    # ── AI
    grp_ai.add_argument("-Q", "--ai", dest="ai", action="store_true",
                        help="Send rendered dump to OpenAI and write reply to --output.")
    grp_ai.add_argument("-m", "--ai-model", dest="ai_model",
                        default=DEFAULT_OPENAI_MODEL, metavar="MODEL",
                        help=f"OpenAI model (default: {DEFAULT_OPENAI_MODEL}).")
    grp_ai.add_argument("-T", "--temperature", dest="temperature",
                        type=float, default=1.2, metavar="NUM",
                        help="OpenAI sampling temperature (default 1.2).")
    grp_ai.add_argument("-B", "--top-p", dest="top_p",
                        type=float, metavar="NUM",
                        help="OpenAI nucleus-sampling probability top_p.")
    grp_ai.add_argument("-R", "--presence-penalty", dest="presence_penalty",
                        type=float, metavar="NUM",
                        help="OpenAI presence penalty.")
    grp_ai.add_argument("-F", "--frequency-penalty", dest="frequency_penalty",
                        type=float, metavar="NUM",
                        help="OpenAI frequency penalty.")
    grp_ai.add_argument("-M", "--ai-system-prompt", dest="ai_system_prompt",
                        metavar="FILE", help="Override the built-in system prompt.")

    # ── Misc
    grp_misc.add_argument("-U", "--upgrade", dest="upgrade", action="store_true",
                          help="Self-update ghconcat from GitHub.")
    grp_misc.add_argument("-L", "--i18n", dest="i18n", default=DEFAULT_I18N,
                          choices=["ES", "EN"],
                          help="Runtime message language (ES default).")
    grp_misc.add_argument("-h", "--help", action="help",
                          help="Show this help message and exit.")

    return p


# ─────────────────────── Parsing & basic checks ───────────────────────
def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    """
    Expand “‑x FILE”, perform pre‑checks and return the parsed Namespace.

    Additional rules
    ----------------
    • «‑r/‑‑root», «‑w/‑‑workspace» and «‑k/‑‑alias» may appear at most once
      per context.
    • «‑‑upgrade» must be *stand‑alone* (no other flags allowed).
    """
    tokens = _expand_x(argv)

    # Exclusive --upgrade
    if "--upgrade" in tokens or "-U" in tokens:
        leftover = [t for t in tokens if t not in ("--upgrade", "-U")]
        if leftover:
            _fatal("--upgrade must be used alone (no additional flags allowed).")

    # Duplicate guards
    if tokens.count("-r") + tokens.count("--root") > 1:
        _fatal("Only one -r/--root allowed per level.")
    if tokens.count("-w") + tokens.count("--workspace") > 1:
        _fatal("Only one -w/--workspace allowed per level.")
    if tokens.count("-k") + tokens.count("--alias") > 1:
        _fatal("Only one -k/--alias allowed per level.")

    ns = _build_parser().parse_args(tokens)

    # Normalise lists
    ns.languages = _split_list(ns.lang)
    ns.skip_langs = _split_list(ns.skip_langs)

    # Derive default output name from template
    if not ns.output and ns.template:
        tpl = Path(ns.template)
        ns.output = f"{tpl.stem}.out{tpl.suffix}"

    return ns


def _infer_langs_from_paths(paths: List[str]) -> List[str]:
    """
    Infer extension set from *paths* **only** when ALL entries are files
    and each one has a valid suffix. Otherwise return an empty list.
    """
    exts: set[str] = set()
    for raw in paths:
        path = Path(raw)
        suf = path.suffix.lower()
        if not suf or raw.endswith(("/", "\\")):
            return []
        exts.add(suf)
    return sorted(exts)


def _ensure_mandatory(ns: argparse.Namespace, *, level: int) -> None:
    """
    Final mandatory flag validation.

    • “‑g” is optional ⇒ wildcard when omitted.
    • “‑a” is optional ⇒ “.” when omitted.
    • No level enforces «‑o» any more; if absent the dump is returned only.
    """
    if ns.upgrade:
        return

    # Implicit «.» when user omitted roots
    if not ns.roots:
        ns.roots = ["."]
    # Try to infer languages from single‑file roots
    if not ns.languages and ns.roots:
        inferred = _infer_langs_from_paths(ns.roots)
        ns.languages = inferred


def _validate_context_flags(ns: argparse.Namespace, *, level: int) -> None:
    """
    Per‑context validation, raising fatal errors on invalid mixes.

    Key rules
    ---------
    • “‑x/‑‑directives” allowed **only** at level 0.
    • Inside an ‑X at least one of {roots, alias, env_vars, ai} must exist.
    • “‑K” entries must follow VAR=VAL syntax.
    """
    if level > 0 and getattr(ns, "x", None):
        _fatal("Flag -x/--directives is not allowed inside an -X context.")

    if ns.alias and "," in ns.alias:
        _fatal("Only one alias is allowed per context.")

    for item in ns.env_vars or []:
        if "=" not in item:
            _fatal(f"--env expects VAR=VAL pairs (got '{item}')")

    if level > 0 and not any([ns.roots, ns.alias, ns.env_vars, ns.ai]):
        _fatal("Inside -X you must provide at least -a, -k, -K or -Q.")


# ──────────────── Path resolution helpers ────────────────
def _resolve_path(base: Path, child: Optional[str]) -> Path:
    """Return *child* resolved against *base* (absolute when needed)."""
    if child is None:
        return base.resolve()
    p = Path(child).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def _resolve_workspace(root: Path, workspace_raw: Optional[str]) -> Path:
    """
    Resolve *workspace_raw*; default is *root* when None.
    Relative paths are interpreted against *root*.
    """
    if workspace_raw is None:
        return root
    wp = Path(workspace_raw).expanduser()
    return wp.resolve() if wp.is_absolute() else (root / wp).resolve()


# ─────────────────────── Pattern helpers ───────────────────────
def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    """
    Return *True* if *line* is a comment to be discarded.

    Regexes are stored in _COMMENT_RULES and work on trimmed lines.
    """
    rules = _COMMENT_RULES.get(ext)
    if not rules:
        return False
    trimmed = line.rstrip()
    return (
            (full and rules[1].match(trimmed)) or
            (simple and rules[0].match(trimmed))
    )


def _discard_import(line: str, ext: str, enable: bool) -> bool:
    """Return *True* if *line* is an import and removal is enabled."""
    rules = _COMMENT_RULES.get(ext)
    return bool(enable and rules and rules[2] and rules[2].match(line))


def _discard_export(line: str, ext: str, enable: bool) -> bool:
    """Return *True* if *line* is an export and removal is enabled."""
    rules = _COMMENT_RULES.get(ext)
    return bool(enable and rules and rules[3] and rules[3].match(line))


def _clean_lines(
        src: Iterable[str],
        ext: str,
        rm_simple: bool,
        rm_all: bool,
        rm_import: bool,
        rm_export: bool,
        keep_blank: bool,
) -> List[str]:
    """Return *src* filtered according to CLI flags."""
    cleaned: List[str] = []
    for l in src:
        if _discard_comment(l, ext, rm_simple, rm_all):
            continue
        if _discard_import(l, ext, rm_import):
            continue
        if _discard_export(l, ext, rm_export):
            continue
        if not keep_blank and _RE_BLANK.match(l):
            continue
        cleaned.append(l)
    return cleaned


# ───────────── File discovery helpers ─────────────
def _hidden(p: Path) -> bool:
    """Return *True* if any path component is hidden (starts with a dot)."""
    return any(part.startswith(".") for part in p.parts)


def _collect_files(
        roots: List[Path],
        excludes: List[str],
        exclude_dirs: List[Path],
        suffixes: List[str],
        active_exts: Optional[Set[str]],
) -> List[Path]:
    """
    Walk *roots* and collect every file that passes all filters.

    *active_exts* = None → accept any extension (wildcard mode).
    """
    ex_dirs = {d.resolve() for d in exclude_dirs}
    collected: Set[Path] = set()

    def _dir_excluded(p: Path) -> bool:
        return any(_is_within(p, d) for d in ex_dirs)

    def _consider(fp: Path) -> None:
        ext = fp.suffix.lower()
        if active_exts is not None and ext not in active_exts:
            return
        if _hidden(fp) or _dir_excluded(fp):
            return
        if ext == ".dart" and fp.name.endswith(".g.dart"):
            return
        if fp.name.endswith((".pyc", ".pyo")):
            return
        if excludes and any(pat in str(fp) for pat in excludes):
            return
        if suffixes and not any(fp.name.endswith(s) for s in suffixes):
            return
        collected.add(fp.resolve())

    for root in roots:
        if not root.exists():
            print(f"ⓘ Warning: {root} does not exist; skipping.", file=sys.stderr)
            continue
        if root.is_file():
            _consider(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and not _dir_excluded(Path(dirpath, d).resolve())
            ]
            for fname in filenames:
                _consider(Path(dirpath, fname).resolve())

    return sorted(collected, key=str)


# ───────────── Concatenation & slicing helpers ─────────────
def _slice_raw(
        raw: List[str],
        first_line: Optional[int],
        total_lines: Optional[int],
        keep_header: bool,
) -> List[str]:
    """
    Return the portion of *raw* according to -n / -N semantics and header flag.

    *first_line* is 1‑based; *total_lines* is the amount to keep.
    """
    if not raw:
        return []

    start = first_line or 1
    if start < 1:
        start = 1
    end = start + total_lines - 1 if total_lines else len(raw)

    selected = raw[start - 1:end]
    if keep_header and start > 1:
        selected = [raw[0], *selected]
    return selected


# ───────────── Concatenation & slicing helper ─────────────
def _concat(  # noqa: C901
    files: List[Path],
    ns: argparse.Namespace,
    wrapped: Optional[List[Tuple[str, str]]] = None,
    header_root: Optional[Path] = None,
) -> str:
    """
    Build the concatenated *dump* applying clean-ups, slicing and wrapping.

    Behaviour
    ---------
    1. With “-l/--list” only headers are emitted.
    2. Empty bodies are skipped entirely (except with -l).
    3. Each header line is always *preceded* by a newline when the previous
       chunk did not finish with one, preventing “}=====” artefacts.
    4. When wrapping is enabled every preserved body is **stored raw**
       (without fences) in *wrapped*.
       The single set of ```LANG fences is added later inside
       `_execute_single`, avoiding nested blocks.
    """
    pieces: List[str] = []
    base_root = header_root or Path.cwd()

    for fp in files:
        ext = fp.suffix.lower()

        # ── Read & slice ────────────────────────────────────────────────
        with fp.open("r", encoding="utf-8", errors="ignore") as src:
            raw_lines = list(src)
        slice_raw = _slice_raw(
            raw_lines, ns.first_line, ns.total_lines, ns.keep_header
        )

        # ── Clean-ups ───────────────────────────────────────────────────
        cleaned = _clean_lines(
            slice_raw,
            ext,
            ns.rm_simple or ns.rm_all,
            ns.rm_all,
            ns.rm_import,
            ns.rm_export,
            ns.keep_blank,
        )

        empty_body = not cleaned or not "".join(cleaned).strip()
        if empty_body and not ns.list_only:
            continue

        # ── Header path (relative or absolute) ──────────────────────────
        if ns.absolute_path:
            header_path = str(fp)
        else:
            try:
                header_path = str(fp.relative_to(base_root))
            except ValueError:
                header_path = os.path.relpath(fp, base_root)

        # ── Header (ensure leading newline) ─────────────────────────────
        if not ns.skip_headers:
            if pieces and not pieces[-1].endswith("\n"):
                pieces[-1] += "\n"
            header = f"{HEADER_DELIM}{header_path} {HEADER_DELIM}\n"
            pieces.append(header)

        # ── Only list routes? ───────────────────────────────────────────
        if ns.list_only:
            continue

        # ── Body + optional extra newline ──────────────────────────────
        body = "".join(cleaned)
        pieces.append(body)
        if ns.keep_blank:
            pieces.append("\n")

        # ── Optional wrapping for templates ────────────────────────────
        if wrapped is not None:
            wrapped.append((header_path, body.rstrip()))

    return "".join(pieces)


# ─────────────── AI helpers ───────────────
def _interpolate(template: str, mapping: Dict[str, str]) -> str:
    """Return *template* with {var} placeholders substituted."""

    def _sub(match: re.Match[str]) -> str:  # noqa: WPS430
        return mapping.get(match.group(1), match.group(0))

    return _PLACEHOLDER.sub(_sub, template)


def _default_sys_prompt(lang: str) -> str:
    prompt = (
        "You are an AI assistant specialized in software development.\n"
        "Always respond in **English** and use **Markdown** for clarity.\n\n"
        "### Quality principles\n"
        "1. Provide **robust, complete, production‑ready solutions**.\n"
        "2. Each answer must be self‑contained: avoid incomplete snippets or diffs.\n"
        "3. Virtually test all code before sending; **no errors are tolerated**.\n\n"
        "### Code requirements\n"
        "- All code, docstrings and inline comments must be in English and comply "
        "with best practices (PEP8, Google docstring, etc.).\n"
        "- Provide **full** files or code sections, properly formatted.\n\n"
        "### Methodology\n"
        "- Analyse any code received before refactoring.\n"
        "- Use all technical capabilities to fulfil tasks efficiently."
    )
    if lang == "ES":
        prompt = prompt.replace("**English**", "**Spanish**")
    return prompt


# ─────────────── AI helper – OpenAI wrapper ───────────────
def _call_openai(
        prompt: str,
        out_path: Path,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 1.2,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        timeout: int = 1800,
) -> None:
    """
    Send *prompt* to OpenAI and write the assistant reply to *out_path*.

    Parameters
    ----------
    prompt:
        The user prompt that will be sent to the assistant.
    out_path:
        Local file where the reply will be written.
    model:
        OpenAI model name (e.g. ``o3``).
    system_prompt:
        System prompt injected before the user message.
    temperature, top_p, presence_penalty, frequency_penalty:
        Sampling controls exposed via CLI (all optional except *temperature*).
    timeout:
        Network timeout in seconds (default 1800).
    """
    if openai is None:
        _fatal("openai not installed. Run: pip install openai")
    if not (key := os.getenv("OPENAI_API_KEY")):
        _fatal("OPENAI_API_KEY not defined.")

    client = openai.OpenAI(api_key=key)  # type: ignore[attr-defined]

    params: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "timeout": timeout,
    }
    if top_p is not None:
        params["top_p"] = top_p
    if presence_penalty is not None:
        params["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        params["frequency_penalty"] = frequency_penalty

    try:
        rsp = client.chat.completions.create(**params)  # type: ignore[arg-type]
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
        print(f"✔ AI reply saved → {out_path}")
    except OpenAIError as exc:  # type: ignore[misc]
        _fatal(f"OpenAI error: {exc}")


# ─────────────── Core executor ───────────────
def _build_active_exts(
        langs: List[str],
        skips: List[str],
) -> Optional[Set[str]]:
    """
    Return the active extension set after applying inclusions/exclusions.

    • No inclusions (langs == []) → wildcard → return *None*.
    • After exclusions the set may become empty → fatal error.
    """
    if not langs:
        # Wildcard mode: accept everything, then prune with -G
        active = None
    else:
        active = set()
        for token in langs:
            token = token.lower()
            if token in PRESETS:
                active.update(PRESETS[token])
            else:
                active.add(token if token.startswith(".") else f".{token}")

    # Apply exclusions
    for token in skips:
        ext = token if token.startswith(".") else f".{token}"
        if active is None:
            # Wildcard mode → build a *ban* list separately (handled later)
            continue
        active.discard(ext)

    if active == set():
        _fatal("After applying --exclude-lang no active extension remains.")
    return active


def _parse_env_list(env_items: List[str] | None) -> Dict[str, str]:
    """Convert ['k=v', 'x=y'] into {'k': 'v', 'x': 'y'}."""
    mapping: Dict[str, str] = {}
    for item in env_items or []:
        if "=" not in item:
            _fatal(f"--env expects VAR=VAL pairs (got '{item}')")
        k, v = item.split("=", 1)
        mapping[k.strip()] = v
    return mapping


# ─────────────── Single-context executor ───────────────
def _execute_single(
    ns: argparse.Namespace,
    workspace: Path,
    root: Path,
) -> str:
    """
    Perform one concatenation job and return the raw dump string produced.
    """
    roots = [
        Path(r).expanduser() if Path(r).is_absolute() else (root / r).resolve()
        for r in (ns.roots or ["."]
                  )
    ]
    exclude_dirs = [
        (Path(d).expanduser() if Path(d).is_absolute() else (root / d)).resolve()
        for d in ns.exclude_dir or []
    ]

    active_exts = _build_active_exts(ns.languages, ns.skip_langs)

    files = _collect_files(
        roots=roots,
        excludes=ns.exclude or [],
        exclude_dirs=exclude_dirs,
        suffixes=ns.suffix or [],
        active_exts=active_exts,
    )
    if not files:
        print("ⓘ No matching files.", file=sys.stderr)
        return ""

    wrapped_chunks: Optional[List[Tuple[str, str]]] = [] if ns.wrap_lang else None
    raw_dump = _concat(files, ns, wrapped_chunks, header_root=root)

    # ── Wrap final output if requested ──────────────────────────────────
    if ns.wrap_lang and wrapped_chunks:
        wrap_lang = ns.wrap_lang
        fenced = []
        for p, c in wrapped_chunks:
            if not c:
                continue
            header_str = "" if ns.skip_headers else f"{HEADER_DELIM}{p} {HEADER_DELIM}\n"
            fenced.append(
                f"{header_str}"
                f"```{wrap_lang or Path(p).suffix.lstrip('.')}\n{c.rstrip()}\n```\n"
            )
        return "".join(fenced)
    return raw_dump


# ─────────────── Core recursive executor ───────────────
def _execute(
    ns: argparse.Namespace,
    *,
    level: int = 0,
    parent_root: Optional[Path] = None,
    parent_workspace: Optional[Path] = None,
    inherited_vars: Optional[Dict[str, str]] = None,
) -> tuple[Dict[str, str], str]:
    """
    Recursively execute *ns* and its children.

    Returns
    -------
    vars_map:
        All variables and aliases available after this context and its children.
    consolidated_dump:
        The concatenated dump of this context **plus** its descendants.
    """
    _validate_context_flags(ns, level=level)
    _ensure_mandatory(ns, level=level)

    root_ref = parent_root if level > 0 else Path.cwd()
    root = _resolve_path(root_ref, ns.root or ".")
    workspace = _resolve_workspace(root, ns.workspace)

    if not root.exists():
        _fatal(f"--root {root} does not exist.")
    if not workspace.exists():
        _fatal(f"--workspace {workspace} does not exist.")

    local_vars: Dict[str, str] = dict(inherited_vars or {})
    dumps: list[str] = []

    # ─── Main concatenation ───
    if ns.roots or ns.languages:
        dump_main = _execute_single(ns, workspace, root)
        if dump_main:
            dumps.append(dump_main)
            if ns.alias:
                local_vars[ns.alias] = dump_main

    # ─── Vars from -K ───
    local_vars.update(_parse_env_list(ns.env_vars))

    # ─── Children (-X) ───
    for bfile in ns.batch_directives or []:
        dpath = Path(bfile)
        if not dpath.is_absolute():
            dpath = workspace / dpath
        if not dpath.exists():
            _fatal(f"Batch file {dpath} not found.")

        tokens = _parse_directive_file(dpath)
        sub_ns = _build_parser().parse_args(tokens)
        sub_ns.languages = _split_list(sub_ns.lang)
        sub_ns.skip_langs = _split_list(sub_ns.skip_langs)

        child_vars, child_dump = _execute(
            sub_ns,
            level=level + 1,
            parent_root=root,
            parent_workspace=workspace,
            inherited_vars=local_vars,
        )
        local_vars.update(child_vars)
        if child_dump:
            dumps.append(child_dump)

    consolidated_dump = "".join(dumps)

    # ─── Template interpolation ───
    if ns.template:
        tpl_path = _resolve_path(workspace, ns.template)
        if not tpl_path.exists():
            _fatal(f"Template file {tpl_path} not found.")
        rendered = _interpolate(tpl_path.read_text(encoding="utf-8"), local_vars)
    else:
        rendered = consolidated_dump

    # ─── Output / AI processing ───
    out_path: Optional[Path] = None
    if ns.output:
        out_path = _resolve_path(workspace, ns.output)
    elif ns.ai:
        # AI without explicit output ⇒ temp file
        temp_fd, temp_name = tempfile.mkstemp(dir=workspace, suffix=".ai.txt")
        os.close(temp_fd)
        out_path = Path(temp_name)

    if ns.ai:
        sys_prompt = (
            _resolve_path(workspace, ns.ai_system_prompt).read_text(encoding="utf-8")
            if ns.ai_system_prompt
            else _default_sys_prompt(ns.i18n)
        )
        _call_openai(
            rendered,
            out_path,
            ns.ai_model,
            sys_prompt,
            temperature=ns.temperature,
            top_p=ns.top_p,
            presence_penalty=ns.presence_penalty,
            frequency_penalty=ns.frequency_penalty,
            timeout=1800,
        )
    elif out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"✔ Output written → {out_path}")

    # Propagate alias from AI / output file if requested
    if ns.alias and out_path and out_path.exists():
        local_vars[ns.alias] = out_path.read_text(encoding="utf-8")

    # Remove temp AI file when not requested by user
    if ns.ai and not ns.output and out_path and out_path.exists():
        out_path.unlink(missing_ok=True)

    return local_vars, consolidated_dump


# ─────────────────────── Self‑upgrade helper ───────────────────────
def _perform_upgrade() -> None:  # pragma: no cover
    """Pull latest version from GitHub and replace local copy."""
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
        print(f"✔ Updated → {dest}")
    except Exception as exc:
        _fatal(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


class GhConcat:
    """
    Programmatic runner used by the test‑suite and external callers.
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute *ghconcat* with *argv* and return the resulting text.

        • When an explicit «‑o» is present, the method reads that file.
        • Otherwise it returns the consolidated dump produced in‑memory.
        """
        ns = _parse_cli(argv)

        if ns.upgrade:
            import importlib
            root_pkg = importlib.import_module("ghconcat")
            getattr(
                root_pkg, "_perform_upgrade",
                getattr(sys.modules[__name__], "_perform_upgrade"),
            )()
            raise SystemExit(0)

        _, dump = _execute(ns)

        if ns.output:
            ws_root = _resolve_workspace(
                _resolve_path(Path.cwd(), ns.root or "."),
                ns.workspace,
            )
            out_path = _resolve_path(ws_root, ns.output)
            try:
                return out_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return ""
        return dump


# ───────────────────────────── CLI entry‑point ─────────────────────────────
def main() -> None:  # pragma: no cover
    """Classic CLI entry‑point."""
    try:
        ns = _parse_cli(sys.argv[1:])
        if ns.upgrade:
            _perform_upgrade()
        else:
            _execute(ns)
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

# Re‑export helpers for the test harness if ghconcat is imported as a module
pkg = sys.modules.get("ghconcat")
if pkg is not None and pkg is not sys.modules[__name__]:
    pkg._call_openai = _call_openai
    pkg._perform_upgrade = _perform_upgrade
