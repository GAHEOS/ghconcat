#!/usr/bin/env python3
"""
ghconcat – universal source‑code concatenator
============================================

Production release – 2025‑07‑27
--------------------------------
* Strong CLI validation: at least one **language** and one **route** are
  mandatory at each level (except `--upgrade`).
* Precise error messages instead of generic “After applying --skip-lang …”.
* `_validate_sub_ns` enforces presence of `-g` and `-a` and forbids nested
  `-x/-X` in sub‑contexts.
* All previous features kept intact.
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
DEFAULT_RAW_DUMP = ".ghconcat_raw_dump.txt"
DEFAULT_OUTPUT = "dump.txt"
DEFAULT_OPENAI_MODEL = "o3"
DEFAULT_I18N = "ES"

PRESETS: dict[str, set[str]] = {
    "odoo": {".py", ".xml", ".js", ".csv"},
}

_COMMENT_RULES: dict[str, Tuple[re.Pattern, re.Pattern,
Optional[re.Pattern], Optional[re.Pattern]]] = {
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
    """Return *True* if ``DEBUG=1`` is present in the environment."""
    return os.getenv("DEBUG") == "1"


def _is_within(path: Path, parent: Path) -> bool:
    """Return *True* if *parent* is an ancestor of *path*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ─────────────────── Directive‑file expansion (‑x) ───────────────────
def _parse_directive_file(path: Path) -> List[str]:
    """Convert a *batch directive file* into an argv‑like token list."""
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
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            else:  # implicit -a
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def _expand_x(argv: Sequence[str]) -> List[str]:
    """Inline‑expand ``-x FILE`` before *argparse* sees argv."""
    if argv.count("-x") > 1:
        _fatal("Only one -x directive file is allowed.")
    if "-x" in argv and len(argv) > 2:
        _fatal("When -x is specified, no other CLI arguments are permitted.")

    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token == "-x":
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


def _build_parser() -> argparse.ArgumentParser:
    """Return the top‑level CLI parser."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage="%(prog)s [-x FILE] [-X FILE] -g LANG[,LANG...] "
              "[-G LANG] [-r DIR] [-w DIR] [-a PATH]... [OPTIONS]",
    )
    # Pre‑processing
    p.add_argument("-x", metavar="FILE",
                   help="Loads a directive file (level 0 only).")
    p.add_argument("-X", action="append", dest="batch_directives", metavar="FILE",
                   help="Executes a nested batch file (level >0).")

    # Locations
    p.add_argument("-r", "--root", metavar="DIR")
    p.add_argument("-w", "--workspace", metavar="DIR")
    p.add_argument("-a", action="append", dest="roots", metavar="PATH")
    p.add_argument("-e", action="append", dest="exclude", metavar="PAT")
    p.add_argument("-E", action="append", dest="exclude_dir", metavar="DIR")
    p.add_argument("-p", action="append", dest="suffix", metavar="SUF")

    # Languages
    p.add_argument("-g", "--lang", action="append", metavar="LANG")
    p.add_argument("-G", "--skip-lang", action="append", dest="skip_langs", metavar="LANG")

    # Range & behaviour
    p.add_argument("-n", dest="total_lines", type=int, metavar="NUM")
    p.add_argument("-N", dest="first_line", type=int, metavar="START")
    p.add_argument("-H", dest="keep_header", action="store_true")
    p.add_argument("-l", "--list", dest="list_only", action="store_true")
    p.add_argument("-c", dest="rm_simple", action="store_true")
    p.add_argument("-C", dest="rm_all", action="store_true")
    p.add_argument("-S", dest="keep_blank", action="store_true")
    p.add_argument("-i", dest="rm_import", action="store_true")
    p.add_argument("-I", dest="rm_export", action="store_true")
    p.add_argument("-W", "--wrap", dest="wrap_lang", metavar="LANG")

    # Template & output
    p.add_argument("-t", "--template", dest="template", metavar="FILE")
    p.add_argument("-o", "--output", dest="output", metavar="FILE")

    # AI
    p.add_argument("--ai", action="store_true")
    p.add_argument("--ai-model", dest="ai_model", default=DEFAULT_OPENAI_MODEL)
    p.add_argument("-A", "--alias", dest="aliases", action="append", metavar="VAR")
    p.add_argument("-V", "--env", dest="env_vars", action="append", metavar="VAR=VAL")
    p.add_argument("-M", "--ai-system-prompt", dest="ai_system_prompt", metavar="FILE")

    # Misc
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("-L", "--i18n", default=DEFAULT_I18N, choices=["ES", "EN"])
    p.add_argument("-h", "--help", action="help")
    return p


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    """Expand -x directives and parse CLI."""
    ns = _build_parser().parse_args(_expand_x(argv))
    ns.languages = _split_list(ns.lang)
    ns.skip_langs = _split_list(ns.skip_langs)

    if not ns.output:
        if ns.template:
            tpl = Path(ns.template)
            ns.output = f"{tpl.stem}.out{tpl.suffix}"
        else:
            ns.output = DEFAULT_OUTPUT
    return ns


# ─── VALIDATION PATCH ───
def _ensure_mandatory(ns: argparse.Namespace, *, level: int) -> None:
    """Abort if required -g / -a are missing."""
    if ns.upgrade:  # upgrade bypass
        return
    if not ns.languages:
        _fatal("You must specify at least one -g/--lang.")
    if not ns.roots:
        _fatal("You must specify at least one -a PATH.")


# ─────────────────────── Pattern helpers (unchanged) ───────────────────────
def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    rules = _COMMENT_RULES.get(ext)
    return bool(rules and (
            (full and rules[1].match(line)) or
            (simple and rules[0].match(line))
    ))


def _discard_import(line: str, ext: str, enable: bool) -> bool:
    rules = _COMMENT_RULES.get(ext)
    return bool(enable and rules and rules[2] and rules[2].match(line))


def _discard_export(line: str, ext: str, enable: bool) -> bool:
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


# ───────────────────── File discovery helpers ─────────────────────
def _hidden(p: Path) -> bool:
    """Return *True* if any path component starts with a dot."""
    return any(part.startswith(".") for part in p.parts)


def _collect_files(
        roots: List[Path],
        excludes: List[str],
        exclude_dirs: List[Path],
        suffixes: List[str],
        active_exts: Set[str],
) -> List[Path]:
    """
    Walk *roots* and collect every file that passes all filters.

    *exclude_dirs* must be absolute paths.
    """
    ex_dirs = {d.resolve() for d in exclude_dirs}
    collected: Set[Path] = set()

    def _dir_excluded(p: Path) -> bool:
        return any(_is_within(p, d) for d in ex_dirs)

    def _consider(fp: Path) -> None:
        ext = fp.suffix.lower()
        if ext not in active_exts or _hidden(fp) or _dir_excluded(fp):
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
            print(f"ⓘ Aviso: {root} no existe; se omite.", file=sys.stderr)
            continue
        if root.is_file():
            _consider(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d
                for d in dirnames
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
    if total_lines:
        end = start + total_lines - 1
    else:
        end = len(raw)

    # Python slices are exclusive on the right
    selected = raw[start - 1:end]
    if keep_header and start > 1:
        selected = [raw[0], *selected]
    return selected


def _concat(
        files: List[Path],
        temp_path: Path,
        ns: argparse.Namespace,
        wrapped: Optional[List[Tuple[str, str]]] = None,
) -> str:
    """
    Concatenate *files* into *temp_path* and optionally collect wrapped chunks.

    Returns the raw dump as a single string (headers included).
    """
    pieces: List[str] = []
    with temp_path.open("w", encoding="utf-8", newline="\n") as out:
        for fp in files:
            ext = fp.suffix.lower()
            with fp.open("r", encoding="utf-8", errors="ignore") as src:
                raw_lines = list(src)
            slice_raw = _slice_raw(
                raw_lines,
                ns.first_line,
                ns.total_lines,
                ns.keep_header,
            )

            lines_clean = _clean_lines(
                slice_raw,
                ext,
                ns.rm_simple or ns.rm_all,
                ns.rm_all,
                ns.rm_import,
                ns.rm_export,
                ns.keep_blank,
            )

            if not any(l.strip() for l in lines_clean) and not ns.list_only:
                continue

            header = f"{HEADER_DELIM}{fp} {HEADER_DELIM}\n"
            pieces.append(header)
            out.write(header)

            body = "" if ns.list_only else "".join(lines_clean)
            if ns.keep_blank:
                out.write("\n")
                pieces.append("\n")
            if body:
                pieces.append(body)
                out.write(body)

            if wrapped is not None:
                wrapped.append((str(fp), body))

    return "".join(pieces)


# ───────────────────────────── AI helpers ─────────────────────────────
def _interpolate(template: str, mapping: Dict[str, str]) -> str:
    """Return *template* with ``{var}`` placeholders substituted."""

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


def _call_openai(
        prompt: str,
        out_path: Path,
        model: str,
        system_prompt: str,
) -> None:
    """Send *prompt* to OpenAI and write the assistant reply to *out_path*."""
    if openai is None:
        _fatal("openai not installed. Run: pip install openai")
    if not (key := os.getenv("OPENAI_API_KEY")):
        _fatal("OPENAI_API_KEY not defined.")
    client = openai.OpenAI(api_key=key)  # type: ignore
    try:
        rsp = client.chat.completions.create(  # type: ignore
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
        print(f"✔ AI reply saved → {out_path}")
    except OpenAIError as exc:  # type: ignore
        _fatal(f"OpenAI error: {exc}")


# ───────────────────────────── Core executor ─────────────────────────────
def _build_active_exts(langs: List[str], skips: List[str]) -> Set[str]:
    """
    Return active extension set after applying inclusions and exclusions.

    Unknown tokens are interpreted as *extensions* (``go`` → ``.go``).
    """
    active: Set[str] = set()
    for token in langs:
        token = token.lower()
        if token in PRESETS:
            active.update(PRESETS[token])
        else:
            active.add(token if token.startswith(".") else f".{token}")
    for token in skips:
        ext = token if token.startswith(".") else f".{token}"
        active.discard(ext)
    if not active:
        _fatal("After applying --skip-lang no active extension remains.")
    return active


def _resolve_path(parent: Path, child: Optional[str]) -> Path:
    """
    Compute effective *child* path relative to *parent*.

    * If *child* is ``None``   → return *parent*.
    * If *child* is absolute   → return *child*.
    * Otherwise                → parent / child.
    """
    if child is None:
        return parent
    cp = Path(child)
    return cp if cp.is_absolute() else (parent / cp).resolve()


def _execute_single(ns: argparse.Namespace, workspace: Path, root: Path) -> str:
    """
    Perform one concatenation job and return the **dump string** produced
    for that context (raw or wrapped, never templated nor AI‑processed).
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

    temp_dump_path = workspace / DEFAULT_RAW_DUMP
    wrapped_chunks: Optional[List[Tuple[str, str]]] = [] if ns.wrap_lang else None
    raw_dump = _concat(files, temp_dump_path, ns, wrapped_chunks)
    print(f"✔ Dump created → {temp_dump_path}")

    if ns.wrap_lang and wrapped_chunks:
        wrap_lang = ns.wrap_lang
        fenced = [
            f"{HEADER_DELIM}{p} {HEADER_DELIM}\n"
            f"```{wrap_lang or Path(p).suffix.lstrip('.')}\n{c.rstrip()}\n```\n"
            for p, c in wrapped_chunks
            if c
        ]
        return "".join(fenced)
    return raw_dump


def _parse_env_list(env_items: List[str] | None) -> Dict[str, str]:
    """Convert ``['k=v', 'x=y']`` into ``{'k': 'v', 'x': 'y'}``."""
    mapping: Dict[str, str] = {}
    for item in env_items or []:
        if "=" not in item:
            _fatal(f"--env expects VAR=VAL pairs (got '{item}')")
        k, v = item.split("=", 1)
        mapping[k.strip()] = v
    return mapping


def _validate_sub_ns(level_ns: argparse.Namespace) -> None:
    """Ensure forbidden flags & mandatory items in level > 0."""
    forbidden = []
    if level_ns.output not in (None, DEFAULT_OUTPUT):
        forbidden.append("--output")
    if level_ns.template:
        forbidden.append("--template")
    if level_ns.ai:
        forbidden.append("--ai")
    if level_ns.ai_model != DEFAULT_OPENAI_MODEL:
        forbidden.append("--ai-model")
    if level_ns.upgrade:
        forbidden.append("--upgrade")
    if level_ns.batch_directives or getattr(level_ns, "x", None):
        forbidden.append("-x/-X")

    if forbidden:
        _fatal(f"Flags {', '.join(forbidden)} are not allowed inside -X contexts.")

    # mandatory flags inside sub‑context
    if not level_ns.lang or not level_ns.roots:
        _fatal("Each -X context must include at least one -g and one -a.")


def _execute(ns: argparse.Namespace) -> None:
    """Handle batches (-X) and self-upgrade."""
    if ns.upgrade:
        pkg = sys.modules.get("ghconcat")
        if pkg is not None and hasattr(pkg, "_perform_upgrade"):
            pkg._perform_upgrade()
        else:
            _perform_upgrade()
        return

    # ¿El nivel 0 sólo orquesta sub-contextos?
    orchestrates_only = bool(ns.batch_directives) and not ns.roots and not ns.languages

    # Validación mandatoria solo si va a procesar archivos en N0
    if not orchestrates_only:
        _ensure_mandatory(ns, level=0)

    workspace = _resolve_path(Path.cwd(), ns.workspace or ".")
    if not workspace.exists():
        _fatal(f"--workspace {workspace} does not exist.")
    root = _resolve_path(workspace, ns.root)
    global_env = _parse_env_list(ns.env_vars)
    prompt_vars: Dict[str, str] = dict(global_env)  # start with env vars

    final_dump_parts: List[str] = []

    # 1. Main job (unless orchestrating only -X)
    orchestrates_only = bool(ns.batch_directives) and not ns.roots
    if not orchestrates_only:
        dump_main = _execute_single(ns, workspace, root)
        if dump_main:
            final_dump_parts.append(dump_main)
            for aname in ns.aliases or []:
                prompt_vars[aname] = dump_main

    # 2. Each -X FILE (level > 0)
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

        if sub_ns.output is None:
            sub_ns.output = DEFAULT_OUTPUT

        _validate_sub_ns(sub_ns)

        if not sub_ns.workspace:
            sub_ns.workspace = str(workspace)
        if not sub_ns.root:
            sub_ns.root = str(root)

        dump_sub = _execute_single(
            sub_ns,
            _resolve_path(workspace, sub_ns.workspace),
            _resolve_path(workspace, sub_ns.root),
        )
        if dump_sub:
            final_dump_parts.append(dump_sub)
            # Alias mapping (one‑to‑one)
            for aname in sub_ns.aliases or []:
                prompt_vars[aname] = dump_sub
        # Env vars from subcontext
        prompt_vars.update(_parse_env_list(sub_ns.env_vars))

    # 3. Consolidated dump (raw or wrapped)
    consolidated_dump = "".join(final_dump_parts)
    prompt_vars.setdefault("dump_data", consolidated_dump)

    out_path = _resolve_path(workspace, ns.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 4. Template & AI handling (only allowed at level 0)
    if ns.template:
        tpl_path = _resolve_path(workspace, ns.template)
        template = tpl_path.read_text(encoding="utf-8")
        rendered = _interpolate(template, prompt_vars)
    else:
        rendered = consolidated_dump

    if ns.ai:
        sys_prompt = (
            _resolve_path(workspace, ns.ai_system_prompt).read_text(encoding="utf-8")
            if ns.ai_system_prompt
            else _default_sys_prompt(ns.i18n)
        )
        _call_openai(rendered, out_path, ns.ai_model, sys_prompt)
    else:
        out_path.write_text(rendered, encoding="utf-8")
        print(f"✔ Output written → {out_path}")


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


# ───────────────────────── Public test API ──────────────────────────
class GhConcat:
    """
    Convenient programmatic runner – used by the test‑suite.
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute *ghconcat* with *argv* and return the final output string.

        The wrapper executes the **full orchestrator** so that ``-X``,
        templates and AI integrations are honoured, and then reads the file
        pointed by ``--output/-o``.
        """
        ns = _parse_cli(argv)
        _execute(ns)
        ws = _resolve_path(Path.cwd(), ns.workspace)
        out = _resolve_path(ws, ns.output)
        try:
            return out.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""  # Defensive – should not happen


# ───────────────────────────── CLI entrypoint ─────────────────────────────
def main() -> None:  # pragma: no cover
    """Classic CLI entry‑point."""
    try:
        ns = _parse_cli(sys.argv[1:])
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
