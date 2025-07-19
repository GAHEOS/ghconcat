#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghconcat
========
Multi‑language concatenator with Odoo / Flutter support, advanced slicing
and orchestration via directive batches.

Highlights
----------
• **Default run** concatenates *.py*, *.xml*, *.js* and *.csv* files
  (see ``DEFAULT_EXTENSIONS``).
• Batch files provided with **-X** may contain several paths on the same
  line and inherit / add / exclude flags from the upper level according
  to the guideline rules.
• -x FILE        Inline directives (expanded before parsing)
• -X FILE        **Batch** directives → independent job, then **merge**
• -r DIR         Base directory for relative routes
• -k EXT         Adds extra extensions (cumulative)
• -n/-N/-H       Line‑range controls
• --ia-*         Sends the consolidated dump to ChatGPT
• --upgrade      Auto‑upgrade from GitHub
• -l/--lang      UI language: ES (default) or EN

Run ``ghconcat -h`` for the full CLI reference.

Error handling
--------------
Tracebacks are hidden unless the environment variable ``DEBUG=1`` is set.

Reminder
--------
Make sure **OPENAI_API_KEY** is exported and «~/.bin» is on your PATH.
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
from typing import Iterable, List, Sequence, Set, Tuple, Optional

# ─────────────────────── Config ────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OUTPUT = "dump.txt"
OPENAI_MODEL = "o3"
DEFAULT_LANGUAGE = "ES"

try:                                 # Lazy OpenAI import
    import openai
    from openai import OpenAIError
except ModuleNotFoundError:          # pragma: no cover
    openai = None                    # A warning will be raised when AI is used
    class OpenAIError(Exception):    # type: ignore
        """Stub exception raised when the OpenAI SDK is missing."""
        pass


# ========== CONTROLLED OUTPUT UTILS ==========
def _fatal(msg: str, code: int = 1) -> None:
    """
    Print *msg* to **STDERR** and exit gracefully without a traceback.

    Parameters
    ----------
    msg:
        Human‑readable error message.
    code:
        Exit status to be returned to the shell (default ``1``).
    """
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    """
    Detect whether the application is running in debug mode.

    Returns
    -------
    bool
        ``True`` when the environment variable ``DEBUG`` is exactly ``"1"``.
    """
    return os.getenv("DEBUG") == "1"


# ───────────────────── Directive expansion ─────────────────────
def _is_within(path: Path, parent: Path) -> bool:
    """
    Check whether *path* belongs to the *parent* subtree.

    Parameters
    ----------
    path:
        Candidate child path.
    parent:
        Directory that may contain *path*.

    Returns
    -------
    bool
        ``True`` if *parent* is an ancestor of *path*.
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _parse_directive_file(path: Path) -> List[str]:
    """
    Parse a batch directive file and convert its contents into CLI tokens.

    Parsing rules
    -------------
    * Comment lines starting with ``#`` or containing ``//`` are ignored.
    * Each word that does **not** begin with a flag is treated as a route and
      expanded as ``"-a", <route>``.
    * Lines that begin with a flag keep that flag. When the flag is ``-a`` and
      more than one argument is provided, every extra value is expanded into an
      independent ``"-a"`` pair so the standard parser can handle them later.

    Parameters
    ----------
    path:
        Absolute path of the directive file.

    Returns
    -------
    list[str]
        A flattened list of tokens suitable for ``argparse``.
    """
    tokens: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            stripped = raw.split("//", 1)[0].strip()
            if not stripped or stripped.startswith("#"):
                continue

            parts = shlex.split(stripped)
            if not parts:
                continue

            # Line begins with a flag
            if parts[0].startswith("-"):
                flag = parts[0]
                # Expand “-a route1 route2 …”
                if flag == "-a" and len(parts) > 2:
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            # Line without flag → treat every word as a route
            else:
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def expand_directives(argv: Sequence[str]) -> List[str]:
    """
    Expand inline ``-x FILE`` tokens.

    Notes
    -----
    * ``-X FILE`` tokens are intentionally **preserved** so that the orchestrator
      can process them at a later stage.
    * Expansion is performed before ``argparse`` consumes the arguments.

    Parameters
    ----------
    argv:
        Raw command‑line arguments excluding ``sys.argv[0]``.

    Returns
    -------
    list[str]
        The argument vector with ``-x`` references expanded.
    """
    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token == "-x":
            try:
                directive_path = Path(next(it))
            except StopIteration:
                _fatal("Error: missing file name after -x.")
            if not directive_path.exists():
                _fatal(f"Error: directive file {directive_path} does not exist.")
            out.extend(_parse_directive_file(directive_path))
        else:
            out.append(token)
    return out


# ─────────────────────── CLI parsing ───────────────────────
def build_parser() -> argparse.ArgumentParser:
    """
    Create and configure the top-level command-line parser for **ghconcat**.

    The parser organises options into thematic groups:

    * **Pre-processing**   – directive files expansion and batch orchestration
    * **Filters**          – roots selection, path exclusion and suffix rules
    * **Slicing**          – line-range extraction and header preservation
    * **Behaviour**        – content clean-up toggles and route-only mode
    * **Extension set**    – inclusion/exclusion of file types
    * **AI integration**   – prompt/output files for ChatGPT interaction
    * **Maintenance**      – self-upgrade from GitHub and localisation
    * **Help**             – standard usage information

    Returns
    -------
    argparse.ArgumentParser
        Fully initialised parser ready to consume user input.
    """
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage=(
            "%(prog)s [-x FILE] [-X FILE] [-a PATH] ... "
            "[-r DIR] [-k EXT] [-l LANG] "
            "[-n NUM] [-N END] [-H] "
            "[--odoo] [--upgrade] "
            "[--ia-prompt FILE --ia-output FILE]"
        ),
    )

    # Pre-processing
    p.add_argument("-x", dest="directives", action="append", metavar="FILE",
                   help="Load additional CLI flags from FILE and process them first.")
    p.add_argument("-X", dest="batch_directives", action="append", metavar="FILE",
                   help="Execute an independent batch defined in FILE and merge its output.")

    # General filters
    p.add_argument("-a", dest="roots", action="append", metavar="PATH",
                   help="Add PATH (file or directory) to the search set.")
    p.add_argument("-r", "--root", dest="base_root", metavar="DIR",
                   help="Base directory used to resolve relative paths.")
    p.add_argument("-e", dest="exclude", action="append", metavar="PAT",
                   help="Skip any path that contains PAT.")
    p.add_argument("-E", dest="exclude_dir", action="append", metavar="DIR",
                   help="Recursively exclude DIR and all its sub-directories.")
    p.add_argument("-p", dest="suffix", action="append", metavar="SUF",
                   help="Restrict the selection to files whose name ends with SUF.")
    p.add_argument("-k", dest="add_ext", action="append", metavar="EXT",
                   help="Register an extra extension (include the dot, e.g. .txt).")
    p.add_argument("-f", dest="output", default=DEFAULT_OUTPUT, metavar="FILE",
                   help=f"Write the final dump to FILE (default: {DEFAULT_OUTPUT}).")

    # Line-range flags
    p.add_argument("-n", dest="range_start_or_len", type=int, metavar="NUM",
                   help="Alone: keep the first NUM lines; with -N, NUM is the 1-based start line.")
    p.add_argument("-N", dest="range_end", type=int, metavar="END",
                   help="1-based end line (inclusive). Requires -n.")
    p.add_argument("-H", dest="keep_header", action="store_true",
                   help="Preserve the first non-blank line (header) even if it falls outside the slice.")

    # Behaviour switches
    p.add_argument("-t", dest="route_only", action="store_true",
                   help="Print matching routes only; do not concatenate file contents.")
    p.add_argument("-c", dest="rm_simple", action="store_true",
                   help="Strip single-line comments.")
    p.add_argument("-C", dest="rm_all", action="store_true",
                   help="Strip all comments, including multi-line doc comments.")
    p.add_argument("-S", dest="keep_blank", action="store_true",
                   help="Preserve blank lines in the output.")
    p.add_argument("-i", dest="rm_import", action="store_true",
                   help="Remove import statements.")
    p.add_argument("-I", dest="rm_export", action="store_true",
                   help="Remove export statements.")

    # Inclusion flags
    p.add_argument("--odoo", dest="alias_odoo", action="store_true",
                   help="Shortcut for --py --xml --js --csv.")
    p.add_argument("--py", dest="inc_py", action="store_true",
                   help="Include Python files (*.py).")
    p.add_argument("--dart", dest="inc_dart", action="store_true",
                   help="Include Dart files (*.dart).")
    p.add_argument("--xml", dest="inc_xml", action="store_true",
                   help="Include XML files (*.xml).")
    p.add_argument("--csv", dest="inc_csv", action="store_true",
                   help="Include CSV files (*.csv).")
    p.add_argument("--js", dest="inc_js", action="store_true",
                   help="Include JavaScript files (*.js).")
    p.add_argument("--yml", dest="inc_yml", action="store_true",
                   help="Include YAML files (*.yml, *.yaml).")

    # Exclusion flags
    p.add_argument("--no-py", dest="no_py", action="store_true",
                   help="Exclude Python files even if previously included.")
    p.add_argument("--no-xml", dest="no_xml", action="store_true",
                   help="Exclude XML files.")
    p.add_argument("--no-js", dest="no_js", action="store_true",
                   help="Exclude JavaScript files.")
    p.add_argument("--no-csv", dest="no_csv", action="store_true",
                   help="Exclude CSV files.")

    # AI integration
    p.add_argument("--ia-prompt", dest="ia_prompt", metavar="FILE",
                   help="Template containing the message to send to ChatGPT (must include {dump_data}).")
    p.add_argument("--ia-output", dest="ia_output", metavar="FILE",
                   help="File where ChatGPT's reply will be saved.")

    # Maintenance
    p.add_argument("--upgrade", dest="upgrade", action="store_true",
                   help="Fetch the latest version from GitHub and replace the local ghconcat.")

    # Internationalisation
    p.add_argument("-l", "--lang", dest="lang", default=DEFAULT_LANGUAGE,
                   choices=["ES", "EN"],
                   help="UI language for prompts and messages: ES (default) or EN.")

    # Help
    p.add_argument("-h", "--help", action="help")
    return p


def parse_cli() -> argparse.Namespace:
    """
    Parse ``sys.argv`` after expanding inline directive files.

    Returns
    -------
    argparse.Namespace
        Fully populated namespace.
    """
    argv = expand_directives(sys.argv[1:])
    ns = build_parser().parse_args(argv)
    ns.lang = ns.lang.upper()
    if ns.lang not in {"ES", "EN"}:
        _fatal("Invalid language: choose ES or EN.")
    return ns


# ───────────────────── Helpers for inheritance ─────────────────────
def _inherit_lists(parent: Optional[List[str]],
                   child: Optional[List[str]]) -> Optional[List[str]]:
    """
    Merge two optional lists according to inheritance rules.

    Returns
    -------
    list[str] | None
        The merged list, or ``None`` when empty.
    """
    merged = (parent or []) + (child or [])
    return merged or None


def inherit_flags(parent: argparse.Namespace, child: argparse.Namespace) -> None:
    """
    Propagate N‑1 flags into N‑2 according to the guideline rules.

    Parameters
    ----------
    parent:
        Namespace from the upper‑level invocation.
    child:
        Namespace corresponding to the sub‑invocation (modified in place).
    """
    # ---- cumulative list flags
    for attr in ("exclude", "exclude_dir", "suffix", "add_ext"):
        setattr(child, attr, _inherit_lists(getattr(parent, attr, None),
                                           getattr(child, attr, None)))

    # ---- boolean flags (OR logic)
    bool_attrs = (
        # inclusion / exclusion
        "alias_odoo", "inc_py", "inc_dart", "inc_xml", "inc_csv", "inc_js",
        "inc_yml", "no_py", "no_xml", "no_js", "no_csv",
        # behaviour switches
        "rm_simple", "rm_all", "keep_blank", "rm_import", "rm_export",
        "route_only", "keep_header"
    )
    for attr in bool_attrs:
        setattr(child, attr, getattr(parent, attr) or getattr(child, attr))

    # ---- range defaults (inherit if child left None)
    if child.range_start_or_len is None:
        child.range_start_or_len = parent.range_start_or_len
    if child.range_end is None:
        child.range_end = parent.range_end
    # (‑H already OR‑merged)


# ───────────────────── Upgrade helper ─────────────────────
def perform_upgrade() -> None:
    """
    Download the latest version of *ghconcat* from GitHub and replace the copy
    located in ``~/.bin``.

    The operation is performed in a temporary directory and works regardless
    of the repository folder structure.
    """
    import stat

    TMP_DIR = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    DEST_DIR = Path.home() / ".bin"
    DEST_FILE = DEST_DIR / "ghconcat"
    REPO_URL = "git@github.com:GAHEOS/ghconcat.git"

    try:
        print(f"Cloning {REPO_URL} …")
        subprocess.check_call(
            ["git", "clone", "--depth", "1", REPO_URL, str(TMP_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        matches = list(TMP_DIR.glob("**/ghconcat.py"))
        if not matches:
            _fatal("No ghconcat.py found in the cloned repository.")

        src = matches[0]                # use the first match
        DEST_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, DEST_FILE)
        DEST_FILE.chmod(DEST_FILE.stat().st_mode | stat.S_IXUSR)

        print(f"✔ ghconcat successfully updated at {DEST_FILE}")
        print("⚠ Make sure ~/.bin is in your PATH and OPENAI_API_KEY is set.")
    except subprocess.CalledProcessError:
        _fatal("git clone failed (wrong URL or access denied?).")
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    sys.exit(0)


# ───────────────────── Extension management ─────────────────────
def active_extensions(ns: argparse.Namespace) -> Set[str]:
    """
    Compute the set of active file extensions after all CLI flags are applied.

    Decision matrix
    ---------------
    1. If **no inclusion flags** are provided, the default set defined in
       ``DEFAULT_EXTENSIONS`` is activated.
    2. Inclusion flags (``--xml``, ``--js``, etc.) add to the set.
    3. Exclusion flags (``--no-xml``, …) remove from the set.
    4. Extra extensions may be appended via ``-k``.

    Parameters
    ----------
    ns:
        Parsed CLI namespace.

    Returns
    -------
    set[str]
        A set of extensions to be considered (including the leading dot).

    Raises
    ------
    SystemExit
        If the resulting set is empty.
    """
    exts: Set[str] = set()
    any_inc = (
        ns.alias_odoo or ns.inc_py or ns.inc_dart or ns.inc_xml or
        ns.inc_csv or ns.inc_js or ns.inc_yml
    )

    # 1. Default behaviour — multi‑extension
    if not any_inc:
        exts.add(".py")

    # 2. Explicit inclusions
    if ns.alias_odoo:
        exts.update({".py", ".xml", ".csv", ".js"})
    if ns.inc_py:
        exts.add(".py")
    if ns.inc_dart:
        exts.add(".dart")
    if ns.inc_xml:
        exts.add(".xml")
    if ns.inc_csv:
        exts.add(".csv")
    if ns.inc_js:
        exts.add(".js")
    if ns.inc_yml:
        exts.update({".yml", ".yaml"})

    # 3. Explicit exclusions
    if ns.no_py:
        exts.discard(".py")
    if ns.no_xml:
        exts.discard(".xml")
    if ns.no_js:
        exts.discard(".js")
    if ns.no_csv:
        exts.discard(".csv")

    # 4. Extra extensions via -k
    if ns.add_ext:
        for ext in ns.add_ext:
            ext = ext if ext.startswith(".") else f".{ext}"
            exts.add(ext.lower())

    if not exts:
        _fatal("Error: no active extension after applying filters.")
    return exts


# ───────────────────── File discovery ─────────────────────
def is_hidden(path: Path) -> bool:
    """
    Determine whether *path* refers to a hidden file or directory.

    Returns
    -------
    bool
        ``True`` if any path component starts with a dot.
    """
    return any(p.startswith(".") for p in path.parts)


def collect_files(roots: List[str],
                  excludes: List[str],
                  exclude_dirs: List[str],
                  suffixes: List[str],
                  extensions: Set[str],
                  explicit_files: Set[Path]) -> List[Path]:
    """
    Discover candidate files applying all active filters.

    Parameters
    ----------
    roots:
        Directories or files supplied by the user.
    excludes:
        Sub‑strings that, when present in the full path, discard the file.
    exclude_dirs:
        Absolute directories to prune from the walk.
    suffixes:
        File‑name suffixes that **must** match (empty means *any*).
    extensions:
        Whitelisted extensions (including the leading dot).
    explicit_files:
        Files that must be kept even if their extension does not match.

    Returns
    -------
    list[pathlib.Path]
        Sorted list of absolute paths that match the criteria.
    """
    found: Set[Path] = set()
    ex_dir_paths = [Path(d).resolve() for d in exclude_dirs]

    def dir_excluded(p: Path) -> bool:
        return any(_is_within(p, ex) for ex in ex_dir_paths)

    def consider(fp: Path) -> None:
        # Always keep explicitly requested files
        if fp in explicit_files:
            found.add(fp)
            return

        fname = fp.name
        ext = fp.suffix.lower()
        if ext not in extensions or is_hidden(fp) or dir_excluded(fp):
            return
        if ext == ".dart" and fname.endswith(".g.dart"):
            return
        if fname.endswith((".pyc", ".pyo")):
            return
        if excludes and any(pat in str(fp) for pat in excludes):
            return
        if suffixes and not any(fname.endswith(s) for s in suffixes):
            return
        found.add(fp.resolve())

    for root in roots:
        p = Path(root)
        if not p.exists():
            print(f"Warning: {root!r} not found — skipped.", file=sys.stderr)
            continue
        if p.is_file():
            consider(p.resolve())
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames
                           if not dir_excluded(Path(dirpath, d).resolve())
                           and not d.startswith(".")]
            for fname in filenames:
                consider(Path(dirpath, fname).resolve())

    return sorted(found, key=str)


# ───── Regex patterns for cleanup ─────
RE_PY_SIMPLE   = re.compile(r"^\s*#(?!#).*$")
RE_PY_FULL     = re.compile(r"^\s*#.*$")
RE_DART_SIMPLE = re.compile(r"^\s*//(?!/).*$")
RE_DART_FULL   = re.compile(r"^\s*//.*$")
RE_BLANK       = re.compile(r"^\s*$")
RE_PY_IMPORT   = re.compile(r"^\s*(?:import\b|from\b.+?\bimport\b)")
RE_DART_IMPORT = re.compile(r"^\s*import\b")
RE_JS_IMPORT   = re.compile(r"^\s*import\b")
RE_DART_EXPORT = re.compile(r"^\s*export\b")
RE_JS_EXPORT   = re.compile(r"^\s*(?:export\b|module\.exports\b)")


def discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    """
    Decide whether *line* should be removed as a comment.

    The decision depends on the file extension and the active switches.

    Parameters
    ----------
    line:
        Raw line read from the source file.
    ext:
        File extension including the leading dot.
    simple:
        Remove *simple* comments (single‑line, non‑doc).
    full:
        Remove **all** comments, including documentation blocks.

    Returns
    -------
    bool
        ``True`` if the line must be discarded.
    """
    if ext == ".py":
        return (full and RE_PY_FULL.match(line)) or (simple and RE_PY_SIMPLE.match(line))
    if ext == ".dart":
        return (full and RE_DART_FULL.match(line)) or (simple and RE_DART_SIMPLE.match(line))
    return False


def discard_import(line: str, ext: str, enable: bool) -> bool:
    """
    Decide whether *line* should be removed because it is an import statement.

    Parameters
    ----------
    line:
        The source line.
    ext:
        File extension.
    enable:
        Master switch (``--rm-import``).

    Returns
    -------
    bool
        ``True`` when the line should be discarded.
    """
    if not enable:
        return False
    return ((ext == ".py" and RE_PY_IMPORT.match(line)) or
            (ext == ".dart" and RE_DART_IMPORT.match(line)) or
            (ext == ".js" and RE_JS_IMPORT.match(line)))


def discard_export(line: str, ext: str, enable: bool) -> bool:
    """
    Decide whether *line* should be removed because it is an export statement.

    Parameters
    ----------
    line:
        The source line.
    ext:
        File extension.
    enable:
        Master switch (``--rm-export``).

    Returns
    -------
    bool
        ``True`` when the line should be discarded.
    """
    if not enable:
        return False
    return ((ext == ".dart" and RE_DART_EXPORT.match(line)) or
            (ext == ".js" and RE_JS_EXPORT.match(line)))


def cleaned_lines(src: Iterable[str],
                  ext: str,
                  rm_simple: bool,
                  rm_all: bool,
                  rm_import: bool,
                  rm_export: bool,
                  keep_blank: bool) -> List[str]:
    """
    Clean the raw source lines according to the provided switches.

    Parameters
    ----------
    src:
        Iterable yielding the original lines.
    ext:
        File extension.
    rm_simple / rm_all / rm_import / rm_export / keep_blank:
        Active clean‑up options.

    Returns
    -------
    list[str]
        The resulting list of lines.
    """
    lines: List[str] = []
    for line in src:
        if discard_comment(line, ext, rm_simple, rm_all):
            continue
        if discard_import(line, ext, rm_import):
            continue
        if discard_export(line, ext, rm_export):
            continue
        if not keep_blank and RE_BLANK.match(line):
            continue
        lines.append(line)
    return lines


# ───────────── Line slicing helpers ─────────────
def compute_slice(total: int,
                  start_or_len: Optional[int],
                  end: Optional[int]) -> Tuple[int, int]:
    """
    Translate CLI ``-n`` / ``-N`` values into a slice tuple.

    Parameters
    ----------
    total:
        Total number of lines available.
    start_or_len:
        When **end** is ``None``, interpreted as *length*, otherwise as
        1‑based *start* index.
    end:
        1‑based inclusive end index.

    Returns
    -------
    tuple[int, int]
        Zero‑based ``(start, end)`` indices; *end* is exclusive.
    """
    if start_or_len is None and end is None:
        return 0, total
    if start_or_len is not None and end is None:
        return 0, min(start_or_len, total)
    if start_or_len is None and end is not None:
        return 0, min(end, total)
    start = max(start_or_len - 1, 0)
    end_index = max(end, start_or_len)
    return start, min(end_index, total)


def apply_range(lines: List[str],
                start_or_len: Optional[int],
                end: Optional[int],
                keep_header: bool) -> List[str]:
    """
    Slice *lines* according to CLI options and optionally prepend the header.

    Parameters
    ----------
    lines:
        Original lines.
    start_or_len / end / keep_header:
        Range options as provided by the CLI.

    Returns
    -------
    list[str]
        The sliced list of lines.
    """
    total = len(lines)
    if total == 0:
        return lines

    begin, finish = compute_slice(total, start_or_len, end)
    sliced = lines[begin:finish]

    if keep_header and lines[0] not in sliced:
        return [lines[0], *sliced]
    return sliced


# ───────────── Concatenation core ─────────────
def concatenate(files: List[Path],
                out_path: Path,
                route_only: bool,
                rm_simple: bool,
                rm_all: bool,
                rm_import: bool,
                rm_export: bool,
                keep_blank: bool,
                range_start_or_len: Optional[int],
                range_end: Optional[int],
                keep_header: bool) -> str:
    """
    Concatenate *files* and write the result to *out_path*.

    Parameters
    ----------
    files:
        Ordered list of absolute paths.
    out_path:
        Destination path (will be overwritten).
    route_only:
        When ``True``, only the file headers are written.
    rm_simple / rm_all / rm_import / rm_export / keep_blank:
        Content clean‑up options.
    range_start_or_len / range_end / keep_header:
        Line‑range options.

    Returns
    -------
    str
        The full dump as a single string (useful for IA).
    """
    out_path = out_path.resolve()
    dump_parts: List[str] = []

    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as out:
            for fp in files:
                if fp == out_path:
                    continue
                ext = fp.suffix.lower()
                with fp.open("r", encoding="utf-8", errors="ignore") as src:
                    raw_lines = cleaned_lines(src, ext,
                                              rm_simple or rm_all, rm_all,
                                              rm_import, rm_export,
                                              keep_blank)
                filtered = apply_range(raw_lines,
                                       range_start_or_len,
                                       range_end,
                                       keep_header)
                if not any(l.strip() for l in filtered):
                    continue
                header = f"{HEADER_DELIM}{fp} {HEADER_DELIM}\n"
                dump_parts.append(header)
                out.write(header)
                if not route_only:
                    body = "".join(filtered) + ("\n" if filtered else "")
                    dump_parts.append(body)
                    out.write(body)
    except (OSError, IOError) as exc:
        _fatal(f"Error writing {out_path}: {exc}")

    return "".join(dump_parts)


# ───────────── IA (OpenAI) ─────────────
def _system_prompt(lang: str) -> str:
    """
    Build the system prompt to be sent to ChatGPT.

    The base text is written in English. When *lang* is ``"ES"``, the word
    **English** is replaced by **Spanish** (and nothing else).

    Parameters
    ----------
    lang:
        ``"EN"`` or ``"ES"`` (upper‑case).

    Returns
    -------
    str
        Fully adapted system prompt.
    """
    prompt = (
        "You are an AI assistant specialized in software development.\n"
        "Always respond in **English** and use **Markdown** to format answers "
        "clearly, concisely, and properly formatted.\n\n"
        "### Quality principles\n"
        "1. Provide **robust, complete, production‑ready solutions**.\n"
        "2. Each answer must be self‑contained: avoid incomplete snippets or "
        "diffs.\n"
        "3. Virtually test all code before sending; **no errors are tolerated**.\n\n"
        "### Code requirements\n"
        "- All code (variable names, functions, classes, etc.), together with "
        "**docstrings** and **inline comments**, must be written in English and "
        "follow best practices (PEP 8, Google Docstring, etc.).\n"
        "- Provide **complete** files or code sections, properly indented and "
        "formatted.\n"
        "- Skip redundant comments: explain only what adds value.\n\n"
        "### Methodology\n"
        "- Thoroughly analyse any code received before refactoring or extending "
        "it.\n"
        "- Use all your technical and computational capabilities to fulfill the "
        "assigned tasks with maximum efficiency and precision."
    )
    if lang == "ES":
        prompt = prompt.replace("**English**", "**Spanish**")
    return prompt


def run_openai(prompt_path: Path,
               output_path: Path,
               dump: str,
               lang: str) -> None:
    """
    Send *dump* to ChatGPT using the template in *prompt_path*.

    Parameters
    ----------
    prompt_path:
        Path to the user prompt template (must contain ``{dump_data}``).
    output_path:
        File where the assistant reply will be written.
    dump:
        Source dump produced by :func:`concatenate`.
    lang:
        UI language chosen by the user (``"ES"`` or ``"EN"``).

    Raises
    ------
    SystemExit
        Whenever a blocking error occurs.
    """
    if openai is None:
        _fatal("OpenAI is not installed. Run: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _fatal("Environment variable OPENAI_API_KEY is not set.")
    try:
        template = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        _fatal(f"Could not read {prompt_path}: {exc}")
    if "{dump_data}" not in template:
        _fatal(f"Placeholder {{dump_data}} not found in {prompt_path}.")

    user_msg = template.replace("{dump_data}", dump)
    client = openai.OpenAI(api_key=api_key)
    print("Contacting OpenAI…")
    try:
        comp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _system_prompt(lang)},
                {"role": "user", "content": user_msg}
            ],
            timeout=120,
        )
        resp = comp.choices[0].message.content
        output_path.write_text(resp, encoding="utf-8")
        print(f"ChatGPT response written → {output_path}")
    except OpenAIError as exc:
        _fatal(f"OpenAI error: {exc}")
    except Exception as exc:           # pragma: no cover
        if _debug_enabled():
            raise
        _fatal(f"Unexpected error while calling OpenAI: {exc}")


# ───────────── Helper for re‑usable internal run ─────────────
def perform_concatenation(ns: argparse.Namespace,
                          base_root: Path,
                          override_output: Optional[Path] = None) -> str:
    """
    Execute a single concatenation job according to *ns*.

    Parameters
    ----------
    ns:
        Active CLI namespace.
    base_root:
        Base directory used to resolve relative paths.
    override_output:
        Destination file to be used instead of ``ns.output`` (typically a
        temporary file when running sub‑jobs).

    Returns
    -------
    str
        The dump generated by :func:`concatenate` or an empty string when no
        file matched.
    """
    # Prepare roots list and explicit files
    if ns.batch_directives:   # nested batches aren’t allowed
        _fatal("Error: nested -X directives are not allowed.")

    raw_roots = ns.roots or [str(base_root)]
    resolved_roots: List[str] = []
    explicit_files: Set[Path] = set()
    for r in raw_roots:
        p = Path(r)
        if not p.is_absolute():
            p = base_root / p
        p = p.resolve()
        resolved_roots.append(str(p))
        if p.is_file():
            explicit_files.add(p)

    # Exclude directories
    exclude_dirs: List[str] = []
    for d in ns.exclude_dir or []:
        p = Path(d)
        if not p.is_absolute():
            p = base_root / p
        exclude_dirs.append(str(p.resolve()))

    exts = active_extensions(ns)
    files = collect_files(
        roots=resolved_roots,
        excludes=ns.exclude or [],
        exclude_dirs=exclude_dirs,
        suffixes=ns.suffix or [],
        extensions=exts,
        explicit_files=explicit_files,
    )
    if not files:
        return ""  # silently return empty dump

    tmp_out = override_output or Path(ns.output)
    dump = concatenate(
        files,
        out_path=tmp_out,
        route_only=ns.route_only,
        rm_simple=bool(ns.rm_simple or ns.rm_all),
        rm_all=bool(ns.rm_all),
        rm_import=ns.rm_import,
        rm_export=ns.rm_export,
        keep_blank=ns.keep_blank,
        range_start_or_len=ns.range_start_or_len,
        range_end=ns.range_end,
        keep_header=ns.keep_header,
    )
    return dump


# ────────────────────────── main ──────────────────────────
def main() -> None:
    """
    Entry point for the *ghconcat* CLI.

    The procedure is:

    1. Parse command‑line arguments.
    2. Run *--upgrade* if requested and exit.
    3. Validate --ia-* parameters.
    4. Perform the main concatenation and any ``-X`` sub‑jobs.
    5. Aggregate all dumps into the final output file.
    6. Optionally invoke ChatGPT.

    Keyboard interrupts and broken pipes are handled gracefully.
    """
    ns = parse_cli()

    # --upgrade takes precedence over everything else.
    if ns.upgrade:
        perform_upgrade()

    # Validate IA flags pair
    if bool(ns.ia_prompt) ^ bool(ns.ia_output):
        _fatal("You must provide both --ia-prompt and --ia-output.")

    base_root = Path(ns.base_root).resolve() if ns.base_root else Path.cwd()

    # Decide whether the main invocation should act as concat itself
    orchestrates_only = bool(ns.batch_directives) and not ns.roots

    final_parts: List[str] = []

    # 1. If main invocation has its own roots, run it first
    if not orchestrates_only:
        tmp_dest = Path(tempfile.mktemp(prefix="ghconcat_main_", suffix=".tmp"))
        part = perform_concatenation(ns, base_root, override_output=tmp_dest)
        tmp_dest.unlink(missing_ok=True)
        if part:
            final_parts.append(part)

    # 2. Process each -X FILE
    for dfile in ns.batch_directives or []:
        dpath = Path(dfile)
        if not dpath.exists():
            _fatal(f"Error: directive file {dpath} does not exist.")

        tokens = _parse_directive_file(dpath)
        sub_ns = build_parser().parse_args(tokens)

        # Neutralise IA and output for sub‑runs
        sub_ns.ia_prompt = None
        sub_ns.ia_output = None
        sub_ns.batch_directives = None     # forbid nesting

        # Inherit root if not given
        if not sub_ns.base_root and ns.base_root:
            sub_ns.base_root = ns.base_root

        # ---- Merge flags from N‑1 into this sub‑namespace
        inherit_flags(ns, sub_ns)

        tmp_dest = Path(tempfile.mktemp(prefix="ghconcat_sub_", suffix=".tmp"))
        part = perform_concatenation(sub_ns,
                                     base_root=Path(sub_ns.base_root).resolve()
                                     if sub_ns.base_root else base_root,
                                     override_output=tmp_dest)
        tmp_dest.unlink(missing_ok=True)
        if part:
            final_parts.append(part)

    # 3. Consolidate and write to final output
    consolidated_dump = "".join(final_parts)
    out_path = Path(ns.output).resolve()
    try:
        out_path.write_text(consolidated_dump, encoding="utf-8")
    except OSError as exc:
        _fatal(f"Error writing {out_path}: {exc}")
    print(f"Concatenation complete → {out_path}")

    # 4. Optional IA
    if ns.ia_prompt:
        run_openai(
            prompt_path=Path(ns.ia_prompt),
            output_path=Path(ns.ia_output),
            dump=consolidated_dump,
            lang=ns.lang,
        )


# ─────────────────────── safe‑entrypoint ───────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _fatal("Keyboard interrupt (Ctrl‑C) — operation cancelled.", 130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:           # pragma: no cover
        if _debug_enabled():
            raise
        _fatal(f"Unexpected error: {exc}")