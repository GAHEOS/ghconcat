#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghconcat
========

Concatenador multi‑lenguaje con soporte Odoo / Flutter y post‑procesado IA.

• -x FILE      lee directivas externas
• -E DIR       excluye árbol completo
• --upgrade    actualiza la herramienta desde «git@github.com:GAHEOS/ghconcat»
• --ia-*       envía el dump resultante a ChatGPT

Manejo de errores
-----------------
Se suprimen los tracebacks para la mayoría de fallos.
Para depurar, exporta  DEBUG=1  antes de ejecutar.

Recordatorio
------------
Debes exportar **OPENAI_API_KEY** en tu entorno y añadir «~/.bin» al PATH
(p.ej. en ~/.bashrc, ~/.zshrc, ~/.zprofile, etc.).
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
from typing import Iterable, List, Sequence, Set

# ─────────────────────── Config ────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OUTPUT = "dump.txt"
OPENAI_MODEL = "gpt-4o"

try:                                 # Import perezoso de OpenAI
    import openai
    from openai import OpenAIError
except ModuleNotFoundError:          # pragma: no cover
    openai = None                    # se avisa al usar IA
    class OpenAIError(Exception):    # type: ignore
        pass

# ========== UTILIDAD DE SALIDA CONTROLADA ==========
def _fatal(msg: str, code: int = 1) -> None:
    """Imprime *msg* en STDERR y termina sin traceback."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    return os.getenv("DEBUG") == "1"


# ───────────────────── Directive expansion ─────────────────────
def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def expand_directives(argv: Sequence[str]) -> List[str]:
    """Sustituye cada «-x file» por los tokens leídos desde *file*."""
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


def _parse_directive_file(path: Path) -> List[str]:
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


# ─────────────────────── CLI parsing ───────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ghconcat",
        add_help=False,
        usage=("%(prog)s [-x FILE] [-a PATH] ... "
               "[--odoo] [--upgrade] "
               "[--ia-prompt FILE --ia-output FILE]"),
    )

    # Pre‑processing
    p.add_argument("-x", dest="directives", action="append", metavar="FILE",
                   help="leer flags adicionales desde FILE (se procesan primero)")

    # General filters
    p.add_argument("-a", dest="roots", action="append", metavar="PATH")
    p.add_argument("-e", dest="exclude", action="append", metavar="PAT")
    p.add_argument("-E", dest="exclude_dir", action="append", metavar="DIR",
                   help="excluir directorio completo")
    p.add_argument("-p", dest="suffix", action="append", metavar="SUF")
    p.add_argument("-f", dest="output", default=DEFAULT_OUTPUT, metavar="FILE")

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
    argv = expand_directives(sys.argv[1:])
    return build_parser().parse_args(argv)


# ───────────────────── Upgrade helper ─────────────────────
def perform_upgrade() -> None:
    """Clona la última versión y reemplaza ~/.bin/ghconcat."""
    from pathlib import Path
    import shutil, subprocess, tempfile, stat, sys, os, glob

    tmp = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    dest_dir = Path.home() / ".bin"
    dest = dest_dir / "ghconcat"

    try:
        url = "git@github.com:GAHEOS/ghconcat"
        print(f"Clonando {url} …")
        subprocess.check_call(["git", "clone", "--depth", "1", url, str(tmp)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Busca el script en cualquier subdirectorio
        matches = list(tmp.glob("**/ghconcat.py"))
        if not matches:
            _fatal("No se encontró ghconcat.py en el repositorio clonado.")
        src = matches[0]  # usa el primero

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR)

        print(f"✔ ghconcat actualizado en {dest}")
        print("Recuerda tener ~/.bin en tu PATH y OPENAI_API_KEY configurada.")
    except subprocess.CalledProcessError as exc:
        _fatal(f"git clone falló: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


# ───────────────────── Extension management ─────────────────────
def active_extensions(ns: argparse.Namespace) -> Set[str]:
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

    if not exts:
        _fatal("Error: ninguna extensión activa tras aplicar filtros.")
    return exts


# ───────────────────── File discovery ─────────────────────
def is_hidden(path: Path) -> bool:
    return any(p.startswith(".") for p in path.parts)


def collect_files(roots: List[str],
                  excludes: List[str],
                  exclude_dirs: List[str],
                  suffixes: List[str],
                  extensions: Set[str]) -> List[Path]:
    found: Set[Path] = set()
    ex_dir_paths = [Path(d).resolve() for d in exclude_dirs]

    def dir_excluded(p: Path) -> bool:
        return any(_is_within(p, ex) for ex in ex_dir_paths)

    def consider(fp: Path) -> None:
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
            consider(p)
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames
                           if not dir_excluded(Path(dirpath, d).resolve())
                           and not d.startswith(".")]
            for fname in filenames:
                consider(Path(dirpath, fname))

    return sorted(found, key=str)


# ───── Regexes para limpieza ─────
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
    if ext == ".py":
        return (full and RE_PY_FULL.match(line)) or (simple and RE_PY_SIMPLE.match(line))
    if ext == ".dart":
        return (full and RE_DART_FULL.match(line)) or (simple and RE_DART_SIMPLE.match(line))
    return False


def discard_import(line: str, ext: str, enable: bool) -> bool:
    if not enable:
        return False
    return ((ext == ".py" and RE_PY_IMPORT.match(line)) or
            (ext == ".dart" and RE_DART_IMPORT.match(line)) or
            (ext == ".js" and RE_JS_IMPORT.match(line)))


def discard_export(line: str, ext: str, enable: bool) -> bool:
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
                  keep_blank: bool) -> Iterable[str]:
    for line in src:
        if discard_comment(line, ext, rm_simple, rm_all):
            continue
        if discard_import(line, ext, rm_import):
            continue
        if discard_export(line, ext, rm_export):
            continue
        if not keep_blank and RE_BLANK.match(line):
            continue
        yield line


# ───────────── Concatenation ─────────────
def substantive(lines: List[str]) -> bool:
    return any(l.strip() for l in lines)


def concatenate(files: List[Path],
                out_path: Path,
                route_only: bool,
                rm_simple: bool,
                rm_all: bool,
                rm_import: bool,
                rm_export: bool,
                keep_blank: bool) -> str:
    out_path = out_path.resolve()
    dump_parts: List[str] = []

    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as out:
            for fp in files:
                if fp == out_path:
                    continue
                ext = fp.suffix.lower()
                with fp.open("r", encoding="utf-8", errors="ignore") as src:
                    flines = list(cleaned_lines(src, ext,
                                                rm_simple or rm_all, rm_all,
                                                rm_import, rm_export,
                                                keep_blank))
                if not substantive(flines):
                    continue
                header = f"{HEADER_DELIM}{fp} {HEADER_DELIM}\n"
                dump_parts.append(header)
                out.write(header)
                if not route_only:
                    body = "".join(flines) + ("\n" if flines else "")
                    dump_parts.append(body)
                    out.write(body)
    except (OSError, IOError) as exc:
        _fatal(f"Error escribiendo {out_path}: {exc}")

    print(f"Concatenation complete → {out_path}")
    return "".join(dump_parts)


# ───────────── IA (OpenAI) ─────────────
def run_openai(prompt_path: Path, output_path: Path, dump: str) -> None:
    if openai is None:
        _fatal("OpenAI no instalado.  Ejecuta: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")  # ← variable oficial
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
                 "content": "Eres un asistente experto en software. Responde en español usando Markdown."},
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


# ────────────────────────── main ──────────────────────────
def main() -> None:
    ns = parse_cli()

    # --upgrade ataja todo lo demás.
    if ns.upgrade:
        perform_upgrade()

    if bool(ns.ia_prompt) ^ bool(ns.ia_output):
        _fatal("Debes proporcionar ambos: --ia-prompt y --ia-output.")

    exts = active_extensions(ns)
    files = collect_files(
        roots=ns.roots or ["."],
        excludes=ns.exclude or [],
        exclude_dirs=ns.exclude_dir or [],
        suffixes=ns.suffix or [],
        extensions=exts,
    )
    if not files:
        _fatal("No se encontraron archivos que coincidan con los criterios.")

    dump = concatenate(
        files,
        out_path=Path(ns.output),
        route_only=ns.route_only,
        rm_simple=bool(ns.rm_simple or ns.rm_all),
        rm_all=bool(ns.rm_all),
        rm_import=ns.rm_import,
        rm_export=ns.rm_export,
        keep_blank=ns.keep_blank,
    )

    if ns.ia_prompt:
        run_openai(
            prompt_path=Path(ns.ia_prompt),
            output_path=Path(ns.ia_output),
            dump=dump,
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