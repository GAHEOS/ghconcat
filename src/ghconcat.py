#!/usr/bin/env python3
"""
ghconcat – universal source‑code concatenator
============================================

Production release – 2025‑07‑25
--------------------------------
* Unified language flags: ``-g/--lang`` (include) & ``-G/--skip-lang`` (exclude).
* Batch orchestration (``-X FILE``) with full ``--ia-set`` support.
* Spanish UI by default; switch with ``--i18n EN``.
* Public class :class:`GhConcat` for direct invocation in tests.
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
        pass


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
                if parts[0] == "-a" and len(parts) > 2:  # “-a f1 f2 …”
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            else:  # implicit -a
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def _expand_x(argv: Sequence[str]) -> List[str]:
    """Inline‑expand every ``-x FILE`` before *argparse* sees argv."""
    # Detect --workspace for relative -x paths
    workspace: Optional[Path] = None
    for i, tok in enumerate(argv):
        if tok in ("-w", "--workspace") and i + 1 < len(argv):
            workspace = Path(argv[i + 1]).expanduser()

    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token == "-x":
            try:
                file_path = Path(next(it))
            except StopIteration:
                _fatal("Error: falta el archivo después de -x.")
            if not file_path.exists() and workspace:
                file_path = workspace / file_path
            if not file_path.exists():
                _fatal(f"Error: {file_path} no existe.")
            out.extend(_parse_directive_file(file_path))
        else:
            out.append(token)
    return out


# ───────────────────────────── CLI parser ─────────────────────────────
def _split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma‑separated tokens."""
    if not raw:
        return []
    out: List[str] = []
    for item in raw:
        out.extend([p.strip() for p in re.split(r"[,\s]+", item) if p.strip()])
    return out


def _build_parser() -> argparse.ArgumentParser:
    """Return the top‑level CLI parser."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage=(
            "%(prog)s [-x FILE] [-X FILE] -g LANG[,LANG...] "
            "[-G LANG] [-r DIR] [-w DIR] [-a PATH]... [otras opciones]"
        ),
    )

    # Pre‑processing
    p.add_argument("-x", action="append", metavar="FILE",
                   help="Carga flags adicionales desde FILE antes de procesar CLI.")
    p.add_argument("-X", action="append", dest="batch_directives", metavar="FILE",
                   help="Ejecuta un batch independiente y fusiona la salida.")

    # Location flags
    p.add_argument("-r", "--root", metavar="DIR",
                   help="Raíz lógica para resolver rutas relativas.")
    p.add_argument("-w", "--workspace", metavar="DIR",
                   help="Directorio de trabajo donde se escriben los resultados.")
    p.add_argument("-a", action="append", dest="roots", metavar="PATH",
                   help="Ruta (archivo o directorio) añadida al set de búsqueda.")
    p.add_argument("-e", action="append", dest="exclude", metavar="PAT",
                   help="Excluye rutas que contengan PAT.")
    p.add_argument("-E", action="append", dest="exclude_dir", metavar="DIR",
                   help="Excluye DIR y sus subdirectorios.")
    p.add_argument("-p", action="append", dest="suffix", metavar="SUF",
                   help="Sólo archivos cuyo nombre termine en SUF.")
    p.add_argument("-k", action="append", dest="add_ext", metavar="EXT",
                   help="Añade extensión extra (incluye el punto).")
    p.add_argument("-f", dest="output", metavar="FILE", default=DEFAULT_OUTPUT,
                   help=f"Escribe el dump en FILE (por defecto {DEFAULT_OUTPUT}).")

    # Languages
    p.add_argument("-g", "--lang", action="append", metavar="LANG",
                   help="Lenguajes a incluir (alias 'odoo'; repetible o CSV).")
    p.add_argument("-G", "--skip-lang", action="append", dest="skip_langs", metavar="LANG",
                   help="Lenguajes a excluir del set activo.")

    # Line range
    p.add_argument("-n", dest="range_start_or_len", type=int, metavar="NUM",
                   help="Sin -N: primeras NUM líneas. Con -N: línea inicial.")
    p.add_argument("-N", dest="range_end", type=int, metavar="END",
                   help="Línea final *exclusiva* (requiere -n).")
    p.add_argument("-H", dest="keep_header", action="store_true",
                   help="Conserva la primera línea no vacía aunque sea recortada.")

    # Behaviour
    p.add_argument("-t", dest="route_only", action="store_true",
                   help="Muestra sólo las rutas coincidentes (sin concatenar).")
    p.add_argument("-c", dest="rm_simple", action="store_true",
                   help="Elimina comentarios de una línea.")
    p.add_argument("-C", dest="rm_all", action="store_true",
                   help="Elimina *todos* los comentarios.")
    p.add_argument("-S", dest="keep_blank", action="store_true",
                   help="Conserva líneas en blanco.")
    p.add_argument("-i", dest="rm_import", action="store_true",
                   help="Elimina sentencias de import.")
    p.add_argument("-I", dest="rm_export", action="store_true",
                   help="Elimina sentencias de export.")

    # AI
    p.add_argument("--ia-prompt", metavar="FILE",
                   help="Plantilla con {dump_data} y otros marcadores.")
    p.add_argument("--ia-output", metavar="FILE",
                   help="Archivo donde guardar la respuesta de ChatGPT.")
    p.add_argument("--ia-model", default=DEFAULT_OPENAI_MODEL, metavar="MODEL",
                   help=f"Modelo de OpenAI (por defecto {DEFAULT_OPENAI_MODEL}).")
    p.add_argument("--ia-set", action="append", metavar="VAR[=VAL]",
                   help="(Sólo en -X) expone {VAR} a la plantilla.")
    p.add_argument("--ia-wrap", metavar="LANG",
                   help="Encierra cada fragmento en bloques ```LANG ...```.")

    # Misc
    p.add_argument("--upgrade", action="store_true", help="Auto‑actualiza ghconcat.")
    p.add_argument("-L", "--i18n", default=DEFAULT_I18N, choices=["ES", "EN"],
                   help="Idioma de mensajes (ES por defecto).")
    p.add_argument("-h", "--help", action="help")

    return p


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    """Expand -x directives and parse CLI into a namespace."""
    ns = _build_parser().parse_args(_expand_x(argv))
    ns.languages = _split_list(ns.lang)
    ns.skip_langs = _split_list(ns.skip_langs)
    return ns


# ─────────────────────── Pattern helpers ────────────────────────
def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    rules = _COMMENT_RULES.get(ext)
    return bool(
        rules and ((full and rules[1].match(line)) or (simple and rules[0].match(line)))
    )


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
def _slice(total: int, start: Optional[int], end: Optional[int]) -> Tuple[int, int]:
    """
    Compute 0‑based (begin, end_exclusive) indices.

    When both *start* and *end* are given we treat *end* as **exclusive** to
    match the expectations of the test‑suite (‑n 50 ‑N 55 ⇒ lines 50‑54).
    """
    if start is None and end is None:
        return 0, total
    if start is not None and end is None:
        return 0, min(start, total)
    if start is None:  # only ‑N
        return 0, min(end - 1, total)
    begin = max(start - 1, 0)
    return begin, min(max(end - 1, start), total)


def _apply_range(lines: List[str], n: Optional[int], N: Optional[int], keep: bool) -> List[str]:
    if not lines:
        return lines
    b, e = _slice(len(lines), n, N)
    part = lines[b:e]
    # Duplicate original first line only if it is outside the slice
    return [lines[0], *part] if keep and b > 0 else part


def _concat(
        files: List[Path],
        out_path: Path,
        ns: argparse.Namespace,
        wrapped: Optional[List[Tuple[str, str]]] = None,
) -> str:
    """
    Concatenate *files* into *out_path* and optionally collect wrapped chunks.

    If *wrapped* is a list, each tuple ``(route, body)`` is appended for IA usage.
    """
    pieces: List[str] = []
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for fp in files:
            ext = fp.suffix.lower()
            with fp.open("r", encoding="utf-8", errors="ignore") as src:
                raw = _clean_lines(
                    src,
                    ext,
                    ns.rm_simple or ns.rm_all,
                    ns.rm_all,
                    ns.rm_import,
                    ns.rm_export,
                    ns.keep_blank,
                )
            lines = _apply_range(raw, ns.range_start_or_len, ns.range_end, ns.keep_header)
            if not any(l.strip() for l in lines):
                continue
            header = f"{HEADER_DELIM}{fp} {HEADER_DELIM}\n"
            pieces.append(header)
            out.write(header)
            if ns.route_only:
                body = ""
            else:
                body = "".join(lines)
            if ns.keep_blank:
                out.write("\n")  # blank entre header y body          # FIX
                pieces.append("\n")  # idem
            if body:
                pieces.append(body)
                out.write(body)
            if wrapped is not None:
                wrapped.append((str(fp), body))
    return "".join(pieces)


# ───────────────────────────── AI helpers ─────────────────────────────
def _interpolate(template: str, mapping: Dict[str, str]) -> str:
    def _sub(match: re.Match[str]) -> str:  # noqa: WPS430
        return mapping.get(match.group(1), match.group(0))

    return _PLACEHOLDER.sub(_sub, template)


def _sys_prompt(lang: str) -> str:
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


def _call_openai(prompt: str, out_path: Path, model: str, lang: str) -> None:
    """Send *prompt* to OpenAI and write the assistant reply to *out_path*."""
    if openai is None:
        _fatal("openai no instalado. Ejecuta: pip install openai")
    if not (key := os.getenv("OPENAI_API_KEY")):
        _fatal("OPENAI_API_KEY no definido.")
    client = openai.OpenAI(api_key=key)  # type: ignore
    try:
        rsp = client.chat.completions.create(  # type: ignore
            model=model,
            messages=[
                {"role": "system", "content": _sys_prompt(lang)},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
        print(f"✔ Respuesta IA guardada → {out_path}")
    except OpenAIError as exc:  # type: ignore
        _fatal(f"Error OpenAI: {exc}")


# ───────────────────────────── Core executor ─────────────────────────────
def _build_active_exts(langs: List[str], skips: List[str], add_ext: List[str]) -> Set[str]:
    """
    Return active extension set after applying inclusions, exclusions and extras.
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
    for ext in add_ext:
        ext = ext if ext.startswith(".") else f".{ext}"
        active.add(ext.lower())
    if not active:
        _fatal("Después de aplicar --skip-lang no queda ninguna extensión activa.")
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
    """Perform one concatenation job and return the resulting dump string."""
    roots = [
        Path(r).expanduser() if Path(r).is_absolute() else (root / r).resolve()
        for r in (ns.roots or ["."]
                  )
    ]

    exclude_dirs = [
        (Path(d).expanduser() if Path(d).is_absolute() else (root / d)).resolve()
        for d in ns.exclude_dir or []
    ]

    active_exts = _build_active_exts(ns.languages, ns.skip_langs, ns.add_ext or [])

    files = _collect_files(
        roots=roots,
        excludes=ns.exclude or [],
        exclude_dirs=exclude_dirs,
        suffixes=ns.suffix or [],
        active_exts=active_exts,
    )
    if not files:
        print("ⓘ No se encontraron archivos para concatenar.", file=sys.stderr)
        return ""

    out_path = Path(ns.output) if Path(ns.output).is_absolute() else workspace / ns.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wrapped_chunks: Optional[List[Tuple[str, str]]] = [] if ns.ia_wrap else None
    dump = _concat(files, out_path, ns, wrapped_chunks)
    print(f"✔ Dump creado → {out_path}")

    # IA integration (only if --ia-prompt at this level)
    if ns.ia_prompt:
        if wrapped_chunks is not None:
            wrap_lang = ns.ia_wrap
            fenced = [
                f"{HEADER_DELIM}{p} {HEADER_DELIM}\n"
                f"```{wrap_lang or Path(p).suffix.lstrip('.')}\n{c.rstrip()}\n```\n"
                for p, c in wrapped_chunks
                if c
            ]
            dump_for_prompt = "".join(fenced)
        else:
            dump_for_prompt = dump

        tpl_path = _resolve_path(workspace, ns.ia_prompt)
        try:
            template = tpl_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover
            _fatal(f"No se pudo leer {tpl_path}: {exc}")

        mapping: Dict[str, str] = {"dump_data": dump_for_prompt}
        for item in ns.ia_set or []:
            if "=" in item:
                k, v = item.split("=", 1)
            else:
                k, v = item, dump_for_prompt
            mapping[k.strip()] = v
        prompt = _interpolate(template, mapping)

        inp_path = tpl_path.with_name(f"{tpl_path.stem}.input{tpl_path.suffix.lstrip('.')}")
        inp_path.write_text(prompt, encoding="utf-8")
        print(f"✔ Prompt interpolado → {inp_path}")

        if ns.ia_output:
            _call_openai(
                prompt, _resolve_path(workspace, ns.ia_output), ns.ia_model, ns.i18n
            )

    return dump


def _execute(ns: argparse.Namespace) -> None:
    """Entry‑point that handles batches (-X) and self‑upgrade."""
    if ns.upgrade:
        pkg = sys.modules.get("ghconcat")
        if pkg is not None and hasattr(pkg, "_perform_upgrade"):
            pkg._perform_upgrade()  # <-- será el fake_upgrade de los tests
        else:
            _perform_upgrade()
        return

    workspace = _resolve_path(Path.cwd(), ns.workspace)
    if not workspace.exists():
        _fatal(f"--workspace {workspace} no existe.")
    root = _resolve_path(workspace, ns.root)

    final_dump_parts: List[str] = []
    prompt_vars: Dict[str, str] = {}

    # 1. Main job (unless only orchestrating -X)
    orchestrates_only = bool(ns.batch_directives) and not ns.roots
    if not orchestrates_only:
        dump_main = _execute_single(ns, workspace, root)
        ns.ia_prompt = None
        ns.ia_output = None
        ns.ia_wrap = None
        if dump_main:
            final_dump_parts.append(dump_main)

    # 2. Each -X FILE
    for bfile in ns.batch_directives or []:
        dpath = Path(bfile)
        if not dpath.is_absolute():  # FIX
            dpath = workspace / dpath
        if not dpath.exists():
            _fatal(f"Error: batch file {dpath} no existe.")
        tokens = _parse_directive_file(dpath)
        sub_ns = _build_parser().parse_args(tokens)
        sub_ns.languages = _split_list(sub_ns.lang)
        sub_ns.skip_langs = _split_list(sub_ns.skip_langs)

        # Prevent recursion & IA calls inside batches
        sub_ns.batch_directives = None
        sub_ns.ia_prompt = None
        sub_ns.ia_output = None
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
            for item in sub_ns.ia_set or []:
                if "=" in item:
                    k, v = item.split("=", 1)
                else:
                    k, v = item, dump_sub
                prompt_vars[k.strip()] = v

    # 3. Consolidate final dump
    consolidated = "".join(final_dump_parts)
    out_path = Path(ns.output) if Path(ns.output).is_absolute() else workspace / ns.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(consolidated, encoding="utf-8")
    print(f"✔ Concatenación final → {out_path}")

    # 4. Top‑level IA prompt (optional)
    if ns.ia_prompt:
        tpl_path = _resolve_path(workspace, ns.ia_prompt)
        template = tpl_path.read_text(encoding="utf-8")
        prompt_vars.setdefault("dump_data", consolidated)
        prompt = _interpolate(template, prompt_vars)
        inp_path = tpl_path.with_name(f"{tpl_path.stem}.input{tpl_path.suffix}")
        inp_path.write_text(prompt, encoding="utf-8")
        print(f"✔ Prompt interpolado → {inp_path}")
        if ns.ia_output:
            _call_openai(
                prompt,
                _resolve_path(workspace, ns.ia_output),
                ns.ia_model,
                ns.i18n,
            )


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
        print(f"✔ Actualizado → {dest}")
    except Exception as exc:
        _fatal(f"Actualización fallida: {exc}")
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
        Execute *ghconcat* with *argv* and return the consolidated dump.

        This wrapper runs the **full orchestrator** (so `-X`, IA, etc. are
        honoured) and then reads the file defined by ``-f/--output``.
        """
        ns = _parse_cli(argv)
        _execute(ns)
        ws = _resolve_path(Path.cwd(), ns.workspace)
        out = Path(ns.output) if Path(ns.output).is_absolute() else ws / ns.output
        try:
            return out.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""  # Defensive – should not happen


# ───────────────────────────── CLI entrypoint ─────────────────────────────
def main() -> None:  # pragma: no cover
    """Classic CLI entry‑point."""
    try:
        ns = _parse_cli(sys.argv[1:])
        _execute(ns)
    except KeyboardInterrupt:
        _fatal("Interrumpido por el usuario.", 130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        if _debug_enabled():
            raise
        _fatal(f"Error inesperado: {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()

pkg = sys.modules.get("ghconcat")
if pkg is not None and pkg is not sys.modules[__name__]:
    pkg._call_openai = _call_openai
    pkg._perform_upgrade = _perform_upgrade
