#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghconcat
========

Multilanguage concatenator with Odoo / Flutter support, advanced slicing
and orchestration via directive batches.

Highlights
----------
• -x FILE        Inline directives (merged in same run)
• -X FILE        **Batch** directives → run as independent job, then merge
• -r DIR         Base directory for resolving *relative* paths
• -k EXT         Add extra extension(s)
• -n/-N/-H       Line‑range controls
• --ia-*         Send resulting dump to ChatGPT
• --upgrade      Self‑update from GitHub

See ``ghconcat -h`` for full CLI reference.

Error handling
--------------
Tracebacks are hidden unless DEBUG=1 is exported.

Reminder
--------
Ensure **OPENAI_API_KEY** is exported and «~/.bin» is in your PATH.
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

try:                                 # Lazy OpenAI import
    import openai
    from openai import OpenAIError
except ModuleNotFoundError:          # pragma: no cover
    openai = None                    # user warned on IA use
    class OpenAIError(Exception):    # type: ignore
        """Stub exception when OpenAI SDK is missing."""
        pass

# ========== CONTROLLED OUTPUT UTILS ==========
def _fatal(msg: str, code: int = 1) -> None:
    """Print *msg* to STDERR and terminate without traceback."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    """Return True when DEBUG=1 is present in the environment."""
    return os.getenv("DEBUG") == "1"


# ───────────────────── Directive expansion ─────────────────────
def _is_within(path: Path, parent: Path) -> bool:
    """Return True if *path* is inside *parent*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _parse_directive_file(path: Path) -> List[str]:
    """Parse an external directive file and return CLI tokens."""
    tokens: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            stripped = raw.split("//", 1)[0].strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = shlex.split(stripped)
            if not parts:
                continue
            if parts[0].startswith("-"):
                tokens.extend(parts)
            else:
                tokens.extend(["-a", stripped])
    return tokens


def expand_directives(argv: Sequence[str]) -> List[str]:
    """
    Expand ``-x FILE`` tokens inline.  ``-X`` tokens are **kept** so that
    the orchestrator can process them later.
    """
    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token == "-x":
            try:
                directive_path = Path(next(it))
            except StopIteration:
                _fatal("Error: faltó el nombre de archivo tras -x.")
            if not directive_path.exists():
                _fatal(f"Error: archivo de directivas {directive_path} no existe.")
            out.extend(_parse_directive_file(directive_path))
        else:
            out.append(token)
    return out


# ─────────────────────── CLI parsing ───────────────────────
def build_parser() -> argparse.ArgumentParser:
    """Return the top‑level argument parser."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage=("%(prog)s [-x FILE] [-X FILE] [-a PATH] ... "
               "[-r DIR] [-k EXT] "
               "[-n NUM] [-N END] [-H] "
               "[--odoo] [--upgrade] "
               "[--ia-prompt FILE --ia-output FILE]"),
    )

    # Pre‑processing
    p.add_argument("-x", dest="directives", action="append", metavar="FILE",
                   help="leer flags adicionales desde FILE (se procesan primero)")
    p.add_argument("-X", dest="batch_directives", action="append", metavar="FILE",
                   help="ejecutar batch independiente según FILE y fusionar su resultado")

    # General filters
    p.add_argument("-a", dest="roots", action="append", metavar="PATH",
                   help="añade archivo/directorio al conjunto de búsqueda")
    p.add_argument("-r", "--root", dest="base_root", metavar="DIR",
                   help="directorio base para resolver rutas relativas")
    p.add_argument("-e", dest="exclude", action="append", metavar="PAT",
                   help="excluye rutas que contengan el patrón dado")
    p.add_argument("-E", dest="exclude_dir", action="append", metavar="DIR",
                   help="excluye directorio completo")
    p.add_argument("-p", dest="suffix", action="append", metavar="SUF",
                   help="solo incluye ficheros cuyo nombre termine en SUF")
    p.add_argument("-k", dest="add_ext", action="append", metavar="EXT",
                   help="añade extensión extra (incluye el punto, ej. .txt)")
    p.add_argument("-f", dest="output", default=DEFAULT_OUTPUT, metavar="FILE",
                   help="archivo de salida (por defecto dump.txt)")

    # Line‑range flags
    p.add_argument("-n", dest="range_start_or_len", type=int, metavar="NUM",
                   help=("si se usa solo, incluye las primeras NUM líneas; "
                         "junto a -N, NUM indica la línea inicial (1‑based)"))
    p.add_argument("-N", dest="range_end", type=int, metavar="END",
                   help="línea final (inclusive) — requiere -n")
    p.add_argument("-H", dest="keep_header", action="store_true",
                   help="conserva la primera línea efectiva (cabecera)")

    # Behaviour switches
    p.add_argument("-t", dest="route_only", action="store_true",
                   help="solo lista rutas (no concatena)")
    p.add_argument("-c", dest="rm_simple", action="store_true",
                   help="elimina comentarios simples")
    p.add_argument("-C", dest="rm_all", action="store_true",
                   help="elimina comentarios simples y de documentación")
    p.add_argument("-S", dest="keep_blank", action="store_true",
                   help="mantiene líneas en blanco")
    p.add_argument("-i", dest="rm_import", action="store_true",
                   help="elimina líneas import")
    p.add_argument("-I", dest="rm_export", action="store_true",
                   help="elimina líneas export")

    # Inclusion flags
    p.add_argument("--odoo", dest="alias_odoo", action="store_true",
                   help="alias para --py --xml --js --csv")
    p.add_argument("--py", dest="inc_py", action="store_true")
    p.add_argument("--dart", dest="inc_dart", action="store_true")
    p.add_argument("--xml", dest="inc_xml", action="store_true")
    p.add_argument("--csv", dest="inc_csv", action="store_true")
    p.add_argument("--js", dest="inc_js", action="store_true")
    p.add_argument("--yml", dest="inc_yml", action="store_true")

    # Exclusion flags
    p.add_argument("--no-py", dest="no_py", action="store_true")
    p.add_argument("--no-xml", dest="no_xml", action="store_true")
    p.add_argument("--no-js", dest="no_js", action="store_true")
    p.add_argument("--no-csv", dest="no_csv", action="store_true")

    # IA
    p.add_argument("--ia-prompt", dest="ia_prompt", metavar="FILE")
    p.add_argument("--ia-output", dest="ia_output", metavar="FILE")

    # Upgrade
    p.add_argument("--upgrade", dest="upgrade", action="store_true",
                   help="descarga la última versión desde GitHub y actualiza ~/.bin/ghconcat")

    # Help
    p.add_argument("-h", "--help", action="help")
    return p


def parse_cli() -> argparse.Namespace:
    """Parse sys.argv, expanding inline directive files first."""
    argv = expand_directives(sys.argv[1:])
    return build_parser().parse_args(argv)


# ───────────────────── Upgrade helper ─────────────────────
def perform_upgrade() -> None:
    """
    Download the latest version from GitHub and replace ~/.bin/ghconcat.
    Works regardless of folder structure inside the repo.
    """
    import shutil
    import stat
    import subprocess
    import tempfile
    from pathlib import Path

    TMP_DIR = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    DEST_DIR = Path.home() / ".bin"
    DEST_FILE = DEST_DIR / "ghconcat"
    REPO_URL = "git@github.com:GAHEOS/ghconcat.git"

    try:
        print(f"Clonando {REPO_URL} …")
        subprocess.check_call(
            ["git", "clone", "--depth", "1", REPO_URL, str(TMP_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        matches = list(TMP_DIR.glob("**/ghconcat.py"))
        if not matches:
            _fatal("No se encontró ningún ghconcat.py en el repositorio clonado.")

        src = matches[0]                # use the first match
        DEST_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, DEST_FILE)

        # Add execute bit for user
        DEST_FILE.chmod(DEST_FILE.stat().st_mode | stat.S_IXUSR)

        print(f"✔ ghconcat actualizado correctamente en {DEST_FILE}")
        print("⚠ Recuerda tener ~/.bin en tu PATH y la variable OPENAI_API_KEY definida.")
    except subprocess.CalledProcessError:
        _fatal("git clone falló (¿URL incorrecta o acceso denegado?).")
    finally:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    sys.exit(0)

# ───────────────────── Extension management ─────────────────────
def active_extensions(ns: argparse.Namespace) -> Set[str]:
    """Return the set of active extensions after processing flags."""
    exts: Set[str] = set()
    any_inc = (
        ns.alias_odoo or ns.inc_py or ns.inc_dart or ns.inc_xml or
        ns.inc_csv or ns.inc_js or ns.inc_yml
    )
    if not any_inc:
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

    # Extra extensions via -k
    if ns.add_ext:
        for ext in ns.add_ext:
            ext = ext if ext.startswith(".") else f".{ext}"
            exts.add(ext.lower())

    if not exts:
        _fatal("Error: ninguna extensión activa tras aplicar filtros.")
    return exts


# ───────────────────── File discovery ─────────────────────
def is_hidden(path: Path) -> bool:
    """Return True when any part of *path* starts with a dot."""
    return any(p.startswith(".") for p in path.parts)


def collect_files(roots: List[str],
                  excludes: List[str],
                  exclude_dirs: List[str],
                  suffixes: List[str],
                  extensions: Set[str],
                  explicit_files: Set[Path]) -> List[Path]:
    """
    Walk *roots* collecting files that match *extensions* and filters.

    *explicit_files* are always included even if their extension does not match.
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
            print(f"Advertencia: {root!r} no encontrado — omitido.", file=sys.stderr)
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


# ───── Regexes for cleanup ─────
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
    """Return True if *line* should be removed as a comment."""
    if ext == ".py":
        return (full and RE_PY_FULL.match(line)) or (simple and RE_PY_SIMPLE.match(line))
    if ext == ".dart":
        return (full and RE_DART_FULL.match(line)) or (simple and RE_DART_SIMPLE.match(line))
    return False


def discard_import(line: str, ext: str, enable: bool) -> bool:
    """Return True if *line* should be removed as an import statement."""
    if not enable:
        return False
    return ((ext == ".py" and RE_PY_IMPORT.match(line)) or
            (ext == ".dart" and RE_DART_IMPORT.match(line)) or
            (ext == ".js" and RE_JS_IMPORT.match(line)))


def discard_export(line: str, ext: str, enable: bool) -> bool:
    """Return True if *line* should be removed as an export statement."""
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
    """Return a list of cleaned lines according to the switches provided."""
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
    Convert CLI -n/-N values into a (start, end) 0‑based slice (end exclusive).
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
    """Return the slice requested and optionally prepend header line."""
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
    Concatenate *files* writing to *out_path* and return the dump string.
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
        _fatal(f"Error escribiendo {out_path}: {exc}")

    return "".join(dump_parts)


# ───────────── IA (OpenAI) ─────────────
def run_openai(prompt_path: Path, output_path: Path, dump: str) -> None:
    """
    Send *dump* to ChatGPT using the prompt template in *prompt_path*.
    """
    if openai is None:
        _fatal("OpenAI no instalado.  Ejecuta: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _fatal("Variable de entorno OPENAI_API_KEY no establecida.")
    try:
        template = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        _fatal(f"No se pudo leer {prompt_path}: {exc}")
    if "{dump_data}" not in template:
        _fatal(f"Placeholder {{dump_data}} no encontrado en {prompt_path}.")

    user_msg = template.replace("{dump_data}", dump)
    client = openai.OpenAI(api_key=api_key)
    print("Contactando con OpenAI…")
    try:
        comp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system",
                 "content": """Eres un asistente de IA experto en desarrollo de software.  
Responde **siempre en español** y utiliza **Markdown** para dar formato a tus respuestas de forma clara y concisa.

### Principios de calidad
1. Entrega **soluciones robustas, completas y listas para producción**.  
2. Cada respuesta debe ser auto-suficiente: evita fragmentos incompletos o «diffs».  
3. Revisa y prueba virtualmente todo el código antes de enviarlo; **no se toleran errores**.

### Requisitos de código
- Todo el código (nombres de variables, funciones, clases, etc.), así como los **docstrings** y **comentarios inline**, deben escribirse **en inglés** y seguir las mejores prácticas del lenguaje (PEP 8, Google Docstring, etc.).  
- Proporciona archivos o secciones de código **completos**, correctamente identados y formateados.  
- Omite comentarios redundantes: explica solo lo que aporte valor.

### Metodología
- Analiza exhaustivamente cualquier código recibido antes de refactorizarlo o ampliarlo.  
- Emplea todas tus capacidades técnicas y computacionales para cumplir las tareas asignadas con la máxima eficacia y precisión."""},
                {"role": "user", "content": user_msg}
            ],
            timeout=120,
        )
        resp = comp.choices[0].message.content
        output_path.write_text(resp, encoding="utf-8")
        print(f"Respuesta ChatGPT escrita → {output_path}")
    except OpenAIError as exc:
        _fatal(f"Error OpenAI: {exc}")
    except Exception as exc:
        if _debug_enabled():
            raise
        _fatal(f"Error inesperado al llamar OpenAI: {exc}")


# ───────────── Helper for re‑usable internal run ─────────────
def perform_concatenation(ns: argparse.Namespace,
                          base_root: Path,
                          override_output: Optional[Path] = None) -> str:
    """
    Execute a concatenation job according to *ns* and return the dump string.

    If *override_output* is given, the dump is written there instead of
    ``ns.output`` (useful for batch‑jobs).
    """
    # Prepare roots list and explicit files
    if ns.batch_directives:   # nested batches aren’t allowed
        _fatal("Error: anidación de -X no permitida.")

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
    """Entry point: parse CLI, orchestrate batches, run IA if needed."""
    ns = parse_cli()

    # --upgrade takes precedence over everything else.
    if ns.upgrade:
        perform_upgrade()

    # Validate IA flags pair
    if bool(ns.ia_prompt) ^ bool(ns.ia_output):
        _fatal("Debes proporcionar ambos: --ia-prompt y --ia-output.")

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
            _fatal(f"Error: archivo de directivas {dpath} no existe.")

        tokens = _parse_directive_file(dpath)
        sub_ns = build_parser().parse_args(tokens)

        # Neutralise IA and output for sub‑runs
        sub_ns.ia_prompt = None
        sub_ns.ia_output = None
        sub_ns.batch_directives = None     # forbid nesting

        # If caller provided --root and sub file did *not*, inherit it
        if not sub_ns.base_root and ns.base_root:
            sub_ns.base_root = ns.base_root

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
        _fatal(f"Error escribiendo {out_path}: {exc}")
    print(f"Concatenation complete → {out_path}")

    # 4. Optional IA
    if ns.ia_prompt:
        run_openai(
            prompt_path=Path(ns.ia_prompt),
            output_path=Path(ns.ia_output),
            dump=consolidated_dump,
        )


# ─────────────────────── safe‑entrypoint ───────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _fatal("Interrupción por teclado (Ctrl‑C) — operación cancelada.", 130)
    except BrokenPipeError:
        sys.exit(0)
    except Exception as exc:
        if _debug_enabled():
            raise
        _fatal(f"Error inesperado: {exc}")