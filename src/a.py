#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ghconcat – generic source‑code concatenator
==========================================

Production‑ready release–2025‑07‑25
-------------------------------------
* **Unified CLI**
  • ``-g/--lang`` Activates one or more language groups (preset *odoo*=.py.xml.js.csv).
  • ``-G/--skip-lang`` Removes languages from the active set.
  • ``-r/--root`` Logical root used to resolve every **relative** ``-a`` path.
  • ``-w/--workspace`` Working directory where every output is written.

* **AI helpers**
  • ``--ia-wrap=<fence>`` Each fragment is wrapped in a Markdown code‑block:

        ===== path/to/file.ext =====
        ```<fence>
        <code>
        ```

* **Unlimited extensibility** – any unknown token passed to ``--lang`` (e.g. *go*)
  automatically activates the corresponding extension (``.go``).

* **Zero legacy flags** –all historical ``--py``, ``--no‑py`` … are gone.

* **Test‑friendly API** –:class:`GhConcat.run()` allows direct invocation from unit‑tests.

The script prints *user‑facing* messages in **Spanish** (per project policy);
all docstrings and inline comments are in **English**.
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

# ─────────────────────────── Constants ───────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OUTPUT = "dump.txt"
DEFAULT_OPENAI_MODEL = "o3"
DEFAULT_I18N = "ES"

# Built‑in language presets
PRESETS: dict[str, set[str]] = {
    "odoo": {".py", ".xml", ".js", ".csv"},
}

# Extensions that have native clean‑up patterns
NATIVE_PATTERNS = {".py", ".dart", ".js", ".yml", ".yaml"}

# ─────────────────────── Optional OpenAI import ──────────────────
try:
    import openai  # type: ignore
    from openai import OpenAIError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore

    class OpenAIError(Exception):  # type: ignore
        """Raised when the OpenAI SDK is unavailable."""
        pass


# ───────────────────────── Aux functions ─────────────────────────
def _fatal(msg: str, code: int = 1) -> None:
    """Print *msg* on **STDERR** and exit gracefully (no traceback)."""
    print(msg, file=sys.stderr)
    sys.exit(code)


def _debug_enabled() -> bool:
    """Return *True* if ``DEBUG=1`` is present in the environment."""
    return os.getenv("DEBUG") == "1"


# ───────────────── Directive‑file expansion (‑x) ─────────────────
def _is_within(path: Path, parent: Path) -> bool:
    """``True`` if *parent* is an ancestor of *path*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


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
            if parts[0].startswith("-"):                         # explicit flag
                if parts[0] == "-a" and len(parts) > 2:           # “-a f1 f2 …”
                    for route in parts[1:]:
                        tokens.extend(["-a", route])
                else:
                    tokens.extend(parts)
            else:                                                # implicit ‑a
                for route in parts:
                    tokens.extend(["-a", route])
    return tokens


def _expand_x(argv: Sequence[str]) -> List[str]:
    """Inline‑expand every ``-x FILE`` before *argparse* sees argv."""
    out: List[str] = []
    it = iter(argv)
    for token in it:
        if token == "-x":
            try:
                file_path = Path(next(it))
            except StopIteration:
                _fatal("Error: falta el archivo después de -x.")
            if not file_path.exists():
                _fatal(f"Error: {file_path} no existe.")
            out.extend(_parse_directive_file(file_path))
        else:
            out.append(token)
    return out


# ────────────────────────── CLIparser ───────────────────────────
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
    p.add_argument("-g", "--lang", required=True, action="append", metavar="LANG",
                   help="Lenguajes a incluir (alias 'odoo'; repetible o CSV).")
    p.add_argument("-G", "--skip-lang", action="append", dest="skip_langs", metavar="LANG",
                   help="Lenguajes a excluir del set activo.")

    # Line range
    p.add_argument("-n", dest="range_start_or_len", type=int, metavar="NUM",
                   help="Sin -N: primeras NUM líneas. Con -N: línea inicial.")
    p.add_argument("-N", dest="range_end", type=int, metavar="END",
                   help="Línea final inclusiva (requiere -n).")
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


# ────────────────── CLI parsing & validation ────────────────────
def _split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma‑separated tokens."""
    if not raw:
        return []
    out: List[str] = []
    for item in raw:
        out.extend([p.strip() for p in re.split(r"[,\s]+", item) if p.strip()])
    return out


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    """Expand -x directives and parse CLI into a namespace."""
    ns = _build_parser().parse_args(_expand_x(argv))
    ns.languages = _split_list(ns.lang)
    ns.skip_langs = _split_list(ns.skip_langs)
    return ns


# ─────────────── Regex patterns for clean‑up ‑ native ────────────
_RE_PY_SIMPLE = re.compile(r"^\s*#(?!#).*$")
_RE_PY_FULL = re.compile(r"^\s*#.*$")
_RE_DART_SL = re.compile(r"^\s*//(?!/).*$")
_RE_DART_FULL = re.compile(r"^\s*//.*$")
_RE_BLANK = re.compile(r"^\s*$")
_RE_PY_IMPORT = re.compile(r"^\s*(?:import\b|from\b.+?\bimport\b)")
_RE_DART_IMPORT = re.compile(r"^\s*import\b")
_RE_DART_EXPORT = re.compile(r"^\s*export\b")
_RE_JS_EXPORT = re.compile(r"^\s*(?:export\b|module\.exports\b)")

_COMMENT_RULES: dict[str, Tuple[re.Pattern, re.Pattern, Optional[re.Pattern], Optional[re.Pattern]]] = {
    ".py": (_RE_PY_SIMPLE, _RE_PY_FULL, _RE_PY_IMPORT, None),
    ".dart": (_RE_DART_SL, _RE_DART_FULL, _RE_DART_IMPORT, _RE_DART_EXPORT),
    ".js": (_RE_DART_SL, _RE_DART_FULL, _RE_DART_IMPORT, _RE_JS_EXPORT),
    ".yml": (_RE_PY_SIMPLE, _RE_PY_FULL, None, None),
    ".yaml": (_RE_PY_SIMPLE, _RE_PY_FULL, None, None),
}


def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    rules = _COMMENT_RULES.get(ext)
    return bool(rules and ((full and rules[1].match(line)) or (simple and rules[0].match(line))))


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


# ─────────────────── File discovery helpers ─────────────────────
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
                d for d in dirnames
                if not d.startswith(".") and not _dir_excluded(Path(dirpath, d).resolve())
            ]
            for fname in filenames:
                _consider(Path(dirpath, fname).resolve())

    return sorted(collected, key=str)


# ───────────────── Concatenation & slicing helpers ───────────────
def _slice(total: int, start_or_len: Optional[int], end: Optional[int]) -> Tuple[int, int]:
    """Compute 0‑based (begin, end_exclusive) indices."""
    if start_or_len is None and end is None:
        return 0, total
    if start_or_len is not None and end is None:
        return 0, min(start_or_len, total)
    if start_or_len is None:
        return 0, min(end, total)
    begin = max(start_or_len - 1, 0)
    return begin, min(max(end, start_or_len), total)


def _apply_range(lines: List[str], n: Optional[int], N: Optional[int], keep: bool) -> List[str]:
    if not lines:
        return lines
    b, e = _slice(len(lines), n, N)
    part = lines[b:e]
    return [lines[0], *part] if keep and lines[0] not in part else part


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
            body = "" if ns.route_only else "".join(lines) + ("\n" if lines else "")
            if body:
                pieces.append(body)
                out.write(body)
            if wrapped is not None:
                wrapped.append((str(fp), body))
    return "".join(pieces)


# ─────────────────────────── AI helpers ──────────────────────────
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][\w\-]*)\}")


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
    if openai is None:
        _fatal("openai no instalado. Ejecuta: pip install openai")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        _fatal("OPENAI_API_KEY no definido.")
    client = openai.OpenAI(api_key=key)  # type: ignore
    try:
        rsp = client.chat.completions.create(  # type: ignore
            model=model,
            messages=[{"role": "system", "content": _sys_prompt(lang)},
                      {"role": "user", "content": prompt}],
            timeout=120,
        )
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
        print(f"✔ Respuesta IA guardada → {out_path}")
    except OpenAIError as exc:  # type: ignore
        _fatal(f"Error OpenAI: {exc}")


# ───────────────────────── Core executor ─────────────────────────
def _execute(ns: argparse.Namespace) -> str:
    """Run ghconcat with the parsed *Namespace* and return consolidated dump."""
    # Workspace & root resolution
    workspace = Path(ns.workspace or Path.cwd()).expanduser()
    if not workspace.is_absolute():
        workspace = (Path.cwd() / workspace).resolve()
    if not workspace.exists():
        _fatal(f"--workspace {workspace} no existe.")
    root_param = Path(ns.root).expanduser() if ns.root else Path(".")
    root = root_param if root_param.is_absolute() else (workspace / root_param).resolve()

    # Build language set
    active_exts: Set[str] = set()
    for token in ns.languages:
        token = token.lower()
        if token in PRESETS:
            active_exts.update(PRESETS[token])
        else:
            ext = token if token.startswith(".") else f".{token}"
            active_exts.add(ext)
    for token in ns.skip_langs:
        ext = token if token.startswith(".") else f".{token}"
        active_exts.discard(ext)
    if not active_exts:
        _fatal("Después de aplicar --skip-lang no queda ninguna extensión activa.")

    # Collect search roots
    raw_roots = ns.roots or ["."]
    roots: List[Path] = []
    for r in raw_roots:
        p = Path(r).expanduser()
        roots.append(p if p.is_absolute() else (root / p))
    roots = [p.resolve() for p in roots]

    exclude_dirs = [
        (Path(d).expanduser() if Path(d).is_absolute() else (root / d)).resolve()
        for d in ns.exclude_dir or []
    ]

    files = _collect_files(
        roots,
        ns.exclude or [],
        exclude_dirs,
        ns.suffix or [],
        active_exts.union({f".{e.lstrip('.')}" for e in ns.add_ext or []}),
    )
    if not files:
        print("ⓘ No se encontraron archivos para concatenar.", file=sys.stderr)
        return ""

    # Concatenate
    out_path = (
        Path(ns.output)
        if Path(ns.output).is_absolute()
        else (workspace / ns.output)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wrapped_chunks: Optional[List[Tuple[str, str]]] = [] if ns.ia_wrap else None
    dump = _concat(files, out_path, ns, wrapped_chunks)
    print(f"✔ Dump creado → {out_path}")

    # AI integration
    if ns.ia_prompt:
        wrap_lang = ns.ia_wrap
        if wrapped_chunks is not None:
            fenced: List[str] = [
                f"{HEADER_DELIM}{p} {HEADER_DELIM}\n```{wrap_lang or Path(p).suffix.lstrip('.')}\n"
                f"{c.rstrip()}\n```\n"
                for p, c in wrapped_chunks if c
            ]
            dump_for_prompt = "".join(fenced)
        else:
            dump_for_prompt = dump

        tpl_path = Path(ns.ia_prompt).expanduser()
        if not tpl_path.is_absolute():
            tpl_path = workspace / tpl_path
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

        inp_path = tpl_path.with_name(f"{tpl_path.stem}.input{tpl_path.suffix}")
        inp_path.write_text(prompt, encoding="utf-8")
        print(f"✔ Prompt interpolado → {inp_path}")

        if ns.ia_output:
            _call_openai(prompt, Path(ns.ia_output), ns.ia_model, ns.i18n)

    return dump


# ────────────────────── Public testing API ──────────────────────
class GhConcat:
    """
    Re‑usable runner, ideal for unit‑tests.

    Example
    -------
    >>> result = GhConcat.run(['-g', 'py', '-a', 'src', '-f', '/tmp/out.txt'])
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute ghconcat programmatically.

        Parameters
        ----------
        argv:
            CLI‑like list (e.g. ``['-g', 'py,dart', '-a', '.', '-w', '.']``).

        Returns
        -------
        str
            Consolidated dump (same content as the file defined by ``-f``).
        """
        ns = _parse_cli(argv)
        return _execute(ns)


# ───────────────────── Self‑upgrade helper ───────────────────────
def _perform_upgrade() -> None:  # pragma: no cover
    import stat

    tmp = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    dest = Path.home() / ".bin" / "ghconcat"
    repo = "git@github.com:GAHEOS/ghconcat.git"

    try:
        subprocess.check_call(["git", "clone", "--depth", "1", repo, str(tmp)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


# ────────────────────────── CLI entrypoint ───────────────────────
def main() -> None:  # pragma: no cover
    try:
        ns = _parse_cli(sys.argv[1:])
        if ns.upgrade:
            _perform_upgrade()
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