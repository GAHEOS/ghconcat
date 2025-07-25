#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghconcat
========
Multi‑language concatenator with Odoo / Flutter support, advanced slicing
and orchestration via directive batches.

Highlights
----------
• **Batch directives** (`-X FILE`) may now declare variables with
  ``--ia-set=<var_name>`` (without value).
  The *dump* produced by that batch becomes available as ``{<var_name>}``
  inside the main ``--ia-prompt`` template.
• These variables do **not** modify *dump.txt* (it still contains the full
  concatenation); they only affect prompt interpolation.
• ``--ia-prompt=my.md`` creates **my.input.md** with every `{placeholder}`
  replaced. The prompt is *not* sent to OpenAI unless ``--ia-output`` is
  provided. ``--ia-model`` lets you change the model (default *o3*).
• All other features remain unchanged (see ``ghconcat -h``).

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
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ─────────────────────── Config ────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OUTPUT = "dump.txt"
DEFAULT_OPENAI_MODEL = "o3"
DEFAULT_LANGUAGE = "ES"

try:                                 # Lazy OpenAI import
    import openai
    from openai import OpenAIError
except ModuleNotFoundError:          # pragma: no cover
    openai = None                    # a stub will be used if the SDK is missing
    class OpenAIError(Exception):    # type: ignore
        """Raised when OpenAI SDK is unavailable."""
        pass


# ========== CONTROLLED OUTPUT UTILS ==========
def _fatal(msg: str, code: int = 1) -> None:
    """Print *msg* to **STDERR** and exit gracefully (no traceback)."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    """Return ``True`` when ``DEBUG=1`` is set in the environment."""
    return os.getenv("DEBUG") == "1"


# ───────────────────── Directive expansion ─────────────────────
def _is_within(path: Path, parent: Path) -> bool:
    """Return ``True`` if *parent* is an ancestor of *path*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _parse_directive_file(path: Path) -> List[str]:
    """Convert a batch file (*path*) into an ``argparse``‑ready token list."""
    tokens: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            stripped = raw.split("//", 1)[0].strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = shlex.split(stripped)
            if not parts:
                continue
            # Leading flag
            if parts[0].startswith("-"):
                flag = parts[0]
                if flag == "-a" and len(parts) > 2:      # expand “-a f1 f2 …”
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            # No flag → every word is a route (-a)
            else:
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def expand_directives(argv: Sequence[str]) -> List[str]:
    """Inline‑expand ``-x FILE`` tokens before ``argparse`` processing."""
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
    """Return the top‑level CLI parser for **ghconcat**."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage=(
            "%(prog)s [-x FILE] [-X FILE] [-a PATH] ... "
            "[-r DIR] [-k EXT] [-l LANG] "
            "[-n NUM] [-N END] [-H] "
            "[--odoo] [--upgrade] "
            "[--ia-prompt FILE [--ia-output FILE] [--ia-model MODEL]]"
        ),
    )

    # Pre‑processing
    p.add_argument("-x", dest="directives", action="append", metavar="FILE",
                   help="Inline: load CLI flags from FILE first.")
    p.add_argument("-X", dest="batch_directives", action="append", metavar="FILE",
                   help="Execute independent batch defined in FILE and merge output.")

    # General filters
    p.add_argument("-a", dest="roots", action="append", metavar="PATH",
                   help="Add PATH (file or directory) to the search set.")
    p.add_argument("-r", "--root", dest="base_root", metavar="DIR",
                   help="Base directory used to resolve relative paths.")
    p.add_argument("-e", dest="exclude", action="append", metavar="PAT",
                   help="Skip any path that contains PAT.")
    p.add_argument("-E", dest="exclude_dir", action="append", metavar="DIR",
                   help="Recursively exclude DIR and its sub‑directories.")
    p.add_argument("-p", dest="suffix", action="append", metavar="SUF",
                   help="Restrict to files whose name ends with SUF.")
    p.add_argument("-k", dest="add_ext", action="append", metavar="EXT",
                   help="Add extra extension (include the dot, e.g. .txt).")
    p.add_argument("-f", dest="output", default=DEFAULT_OUTPUT, metavar="FILE",
                   help=f"Write final dump to FILE (default: {DEFAULT_OUTPUT}).")

    # Line‑range
    p.add_argument("-n", dest="range_start_or_len", type=int, metavar="NUM",
                   help="Alone: keep first NUM lines; with -N, 1‑based start line.")
    p.add_argument("-N", dest="range_end", type=int, metavar="END",
                   help="1‑based inclusive end line (requires -n).")
    p.add_argument("-H", dest="keep_header", action="store_true",
                   help="Preserve first non‑blank line even if sliced out.")

    # Behaviour
    p.add_argument("-t", dest="route_only", action="store_true",
                   help="Print matching routes only (no concatenation).")
    p.add_argument("-c", dest="rm_simple", action="store_true",
                   help="Strip single‑line comments.")
    p.add_argument("-C", dest="rm_all", action="store_true",
                   help="Strip *all* comments (incl. docblocks).")
    p.add_argument("-S", dest="keep_blank", action="store_true",
                   help="Preserve blank lines.")
    p.add_argument("-i", dest="rm_import", action="store_true",
                   help="Remove import statements.")
    p.add_argument("-I", dest="rm_export", action="store_true",
                   help="Remove export statements.")

    # Inclusion
    p.add_argument("--odoo", dest="alias_odoo", action="store_true",
                   help="Shortcut for --py --xml --js --csv.")
    p.add_argument("--py", dest="inc_py", action="store_true",
                   help="Include Python files.")
    p.add_argument("--dart", dest="inc_dart", action="store_true",
                   help="Include Dart files.")
    p.add_argument("--xml", dest="inc_xml", action="store_true",
                   help="Include XML files.")
    p.add_argument("--csv", dest="inc_csv", action="store_true",
                   help="Include CSV files.")
    p.add_argument("--js", dest="inc_js", action="store_true",
                   help="Include JavaScript files.")
    p.add_argument("--yml", dest="inc_yml", action="store_true",
                   help="Include YAML files.")

    # Exclusion
    p.add_argument("--no-py", dest="no_py", action="store_true",
                   help="Exclude Python files.")
    p.add_argument("--no-xml", dest="no_xml", action="store_true",
                   help="Exclude XML files.")
    p.add_argument("--no-js", dest="no_js", action="store_true",
                   help="Exclude JavaScript files.")
    p.add_argument("--no-csv", dest="no_csv", action="store_true",
                   help="Exclude CSV files.")

    # AI integration
    p.add_argument("--ia-prompt", dest="ia_prompt", metavar="FILE",
                   help="Prompt template (placeholders: {dump_data} + each --ia-set).")
    p.add_argument("--ia-output", dest="ia_output", metavar="FILE",
                   help="Where to store ChatGPT reply. If omitted, no call is made.")
    p.add_argument("--ia-model", dest="ia_model", default=DEFAULT_OPENAI_MODEL, metavar="MODEL",
                   help=f"OpenAI model (default: {DEFAULT_OPENAI_MODEL}).")
    p.add_argument("--ia-set", dest="ia_set", action="append", metavar="VAR[=VAL]",
                   help="**For batch files only**: expose dump (or VAL) as {VAR}.")  # ← NEW: flagged as batch‑only

    # Maintenance
    p.add_argument("--upgrade", dest="upgrade", action="store_true",
                   help="Self‑upgrade from GitHub.")

    # I18N
    p.add_argument("-l", "--lang", dest="lang", default=DEFAULT_LANGUAGE,
                   choices=["ES", "EN"],
                   help="UI language: ES (default) or EN.")

    # Help
    p.add_argument("-h", "--help", action="help")
    return p


def parse_cli() -> argparse.Namespace:
    """Parse CLI after inline expansion."""
    argv = expand_directives(sys.argv[1:])
    ns = build_parser().parse_args(argv)
    ns.lang = ns.lang.upper()
    if ns.lang not in {"ES", "EN"}:
        _fatal("Invalid language: choose ES or EN.")
    return ns


# ───────────────────── Helpers for inheritance ─────────────────────
def _inherit_lists(parent: Optional[List[str]],
                   child: Optional[List[str]]) -> Optional[List[str]]:
    """Return combined list or ``None``."""
    merged = (parent or []) + (child or [])
    return merged or None


def inherit_flags(parent: argparse.Namespace, child: argparse.Namespace) -> None:
    """Propagate N‑1 flags into N‑2 according to guideline rules."""
    for attr in ("exclude", "exclude_dir", "suffix", "add_ext"):
        setattr(child, attr, _inherit_lists(getattr(parent, attr, None),
                                           getattr(child, attr, None)))
    bools = (
        "alias_odoo", "inc_py", "inc_dart", "inc_xml", "inc_csv", "inc_js",
        "inc_yml", "no_py", "no_xml", "no_js", "no_csv",
        "rm_simple", "rm_all", "keep_blank", "rm_import", "rm_export",
        "route_only", "keep_header"
    )
    for attr in bools:
        setattr(child, attr, getattr(parent, attr) or getattr(child, attr))
    if child.range_start_or_len is None:
        child.range_start_or_len = parent.range_start_or_len
    if child.range_end is None:
        child.range_end = parent.range_end


# ───────────────────── Upgrade helper ─────────────────────
def perform_upgrade() -> None:
    """Pull latest version from GitHub and replace local copy."""
    import stat

    tmp_dir = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    dest_dir = Path.home() / ".bin"
    dest_file = dest_dir / "ghconcat"
    repo_url = "git@github.com:GAHEOS/ghconcat.git"

    try:
        print(f"Cloning {repo_url} …")
        subprocess.check_call(
            ["git", "clone", "--depth", "1", repo_url, str(tmp_dir)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        matches = list(tmp_dir.glob("**/ghconcat.py"))
        if not matches:
            _fatal("No ghconcat.py found in the cloned repository.")

        src = matches[0]
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_file)
        dest_file.chmod(dest_file.stat().st_mode | stat.S_IXUSR)

        print(f"✔ ghconcat successfully updated → {dest_file}")
        print("⚠ Ensure ~/.bin is in PATH and OPENAI_API_KEY is set.")
    except subprocess.CalledProcessError:
        _fatal("git clone failed (wrong URL or access denied?).")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    sys.exit(0)


# ───────────────────── Extension management ─────────────────────
def active_extensions(ns: argparse.Namespace) -> Set[str]:
    """Return active extensions after inclusion / exclusion flags."""
    exts: Set[str] = set()
    any_inc = (
        ns.alias_odoo or ns.inc_py or ns.inc_dart or ns.inc_xml or
        ns.inc_csv or ns.inc_js or ns.inc_yml
    )

    if not any_inc:                      # default
        exts.add(".py")
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

    if ns.no_py:
        exts.discard(".py")
    if ns.no_xml:
        exts.discard(".xml")
    if ns.no_js:
        exts.discard(".js")
    if ns.no_csv:
        exts.discard(".csv")

    if ns.add_ext:
        for ext in ns.add_ext:
            ext = ext if ext.startswith(".") else f".{ext}"
            exts.add(ext.lower())

    if not exts:
        _fatal("Error: no active extension after applying filters.")
    return exts


# ───────────────────── File discovery ─────────────────────
def is_hidden(path: Path) -> bool:
    """Return ``True`` if *path* has any hidden component."""
    return any(p.startswith(".") for p in path.parts)


def collect_files(roots: List[str],
                  excludes: List[str],
                  exclude_dirs: List[str],
                  suffixes: List[str],
                  extensions: Set[str],
                  explicit_files: Set[Path]) -> List[Path]:
    """Return sorted list of paths that pass all filters."""
    found: Set[Path] = set()
    ex_dir_paths = [Path(d).resolve() for d in exclude_dirs]

    def dir_excluded(p: Path) -> bool:
        return any(_is_within(p, ex) for ex in ex_dir_paths)

    def consider(fp: Path) -> None:
        if fp in explicit_files:         # keep explicit files regardless
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
    """Return ``True`` if *line* should be removed as comment."""
    if ext == ".py":
        return (full and RE_PY_FULL.match(line)) or (simple and RE_PY_SIMPLE.match(line))
    if ext == ".dart":
        return (full and RE_DART_FULL.match(line)) or (simple and RE_DART_SIMPLE.match(line))
    return False


def discard_import(line: str, ext: str, enable: bool) -> bool:
    """Return ``True`` when *line* is an import to be removed."""
    if not enable:
        return False
    return ((ext == ".py" and RE_PY_IMPORT.match(line)) or
            (ext == ".dart" and RE_DART_IMPORT.match(line)) or
            (ext == ".js" and RE_JS_IMPORT.match(line)))


def discard_export(line: str, ext: str, enable: bool) -> bool:
    """Return ``True`` when *line* is an export to be removed."""
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
    """Return list of cleaned lines according to toggles."""
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
    """Return 0‑based ``(start, end)`` (end exclusive) from CLI range flags."""
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
    """Return sliced list of *lines* following -n / -N / -H."""
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
    """Concatenate *files* and write to *out_path*."""
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


# ───────────── IA (OpenAI) helpers ─────────────
def _system_prompt(lang: str) -> str:
    """Return system prompt (English or Spanish UI)."""
    prompt = (
        "You are an AI assistant specialized in software development.\n"
        "Always respond in **English** and use **Markdown** for clarity.\n\n"
        "### Quality principles\n"
        "1. Provide **robust, complete, production‑ready solutions**.\n"
        "2. Each answer must be self‑contained: avoid incomplete snippets or diffs.\n"
        "3. Virtually test all code before sending; **no errors are tolerated**.\n\n"
        "### Code requirements\n"
        "- All code, docstrings and inline comments must be in English and comply "
        "with best practices (PEP 8, Google docstring, etc.).\n"
        "- Provide **full** files or code sections, properly formatted.\n\n"
        "### Methodology\n"
        "- Analyse any code received before refactoring.\n"
        "- Use all technical capabilities to fulfil tasks efficiently."
    )
    if lang == "ES":
        prompt = prompt.replace("**English**", "**Spanish**")
    return prompt


def run_openai(user_msg: str,
               output_path: Path,
               lang: str,
               model: str = DEFAULT_OPENAI_MODEL) -> None:
    """Contact OpenAI and write assistant reply to *output_path*."""
    if openai is None:
        _fatal("OpenAI is not installed. Run: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _fatal("Environment variable OPENAI_API_KEY is not set.")

    client = openai.OpenAI(api_key=api_key)
    print("Contacting OpenAI…")
    try:
        comp = client.chat.completions.create(
            model=model,
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


# ───────────── Template interpolation ─────────────
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][\w\-]*)\}")

def interpolate(template: str, values: Dict[str, str]) -> str:
    """Return *template* with `{placeholders}` replaced by *values*."""
    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name, match.group(0))
    return _PLACEHOLDER.sub(_sub, template)


# ───────────── Helper for reusable internal run ─────────────
def perform_concatenation(ns: argparse.Namespace,
                          base_root: Path,
                          override_output: Optional[Path] = None) -> str:
    """Run a single concatenation job and return its dump."""
    if ns.batch_directives:
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
        return ""

    tmp_out = override_output or Path(ns.output)
    return concatenate(
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


# ────────────────────────── main ──────────────────────────
def _parse_ia_set(item: str, dump_value: str) -> Tuple[str, str]:
    """Return ``(name, value)`` from *item* which can be ``name`` or ``name=val``."""
    if "=" in item:
        n, v = item.split("=", 1)
        return n.strip(), v
    return item.strip(), dump_value


def main() -> None:
    """CLI entry point."""
    ns = parse_cli()

    # --upgrade has top priority
    if ns.upgrade:
        perform_upgrade()

    # --ia-set is forbidden in the top‑level call  # ← NEW validation
    if ns.ia_set:
        _fatal("--ia-set can only be used inside files loaded with -X.")

    # --ia-output depends on --ia-prompt
    if ns.ia_output and not ns.ia_prompt:
        _fatal("--ia-output requires --ia-prompt.")

    base_root = Path(ns.base_root).resolve() if ns.base_root else Path.cwd()
    orchestrates_only = bool(ns.batch_directives) and not ns.roots

    final_parts: List[str] = []
    prompt_vars: Dict[str, str] = {}

    # 1. Main invocation (only if it has its own roots)
    if not orchestrates_only:
        tmp = Path(tempfile.mktemp(prefix="ghconcat_main_", suffix=".tmp"))
        part = perform_concatenation(ns, base_root, override_output=tmp)
        tmp.unlink(missing_ok=True)
        if part:
            final_parts.append(part)

    # 2. Process each -X FILE
    for dfile in ns.batch_directives or []:
        dpath = Path(dfile)
        if not dpath.exists():
            _fatal(f"Error: directive file {dpath} does not exist.")

        tokens = _parse_directive_file(dpath)
        sub_ns = build_parser().parse_args(tokens)

        sub_ns.ia_prompt = None          # ignore IA inside sub‑runs
        sub_ns.ia_output = None
        sub_ns.batch_directives = None
        if not sub_ns.base_root and ns.base_root:
            sub_ns.base_root = ns.base_root

        inherit_flags(ns, sub_ns)

        tmp = Path(tempfile.mktemp(prefix="ghconcat_sub_", suffix=".tmp"))
        part = perform_concatenation(sub_ns,
                                     base_root=Path(sub_ns.base_root).resolve()
                                     if sub_ns.base_root else base_root,
                                     override_output=tmp)
        tmp.unlink(missing_ok=True)
        if part:
            final_parts.append(part)
            for item in sub_ns.ia_set or []:           # ← NEW: gather vars
                name, val = _parse_ia_set(item, part)
                if name in prompt_vars:
                    print(f"Warning: placeholder {name!r} overwritten.", file=sys.stderr)
                prompt_vars[name] = val

    # 3. Consolidate dump.txt
    consolidated = "".join(final_parts)
    out_path = Path(ns.output).resolve()
    try:
        out_path.write_text(consolidated, encoding="utf-8")
    except OSError as exc:
        _fatal(f"Error writing {out_path}: {exc}")
    print(f"Concatenation complete → {out_path}")

    # 4. Prompt handling
    if ns.ia_prompt:
        t_path = Path(ns.ia_prompt)
        try:
            template = t_path.read_text(encoding="utf-8")
        except OSError as exc:
            _fatal(f"Could not read {t_path}: {exc}")

        prompt_vars.setdefault("dump_data", consolidated)
        interpolated = interpolate(template, prompt_vars)

        inp_path = t_path.with_name(f"{t_path.stem}.input{t_path.suffix}")
        try:
            inp_path.write_text(interpolated, encoding="utf-8")
        except OSError as exc:
            _fatal(f"Could not write {inp_path}: {exc}")
        print(f"Interpolated prompt written → {inp_path}")

        if ns.ia_output:
            run_openai(
                user_msg=interpolated,
                output_path=Path(ns.ia_output),
                lang=ns.lang,
                model=ns.ia_model,
            )


# ─────────────────────── safe‑entrypoint ───────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _fatal("Keyboard interrupt — cancelled.", 130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:           # pragma: no cover
        if _debug_enabled():
            raise
        _fatal(f"Unexpected error: {exc}")