#!/usr/bin/env python3
"""
ghconcat – Multi‑level concatenation, slicing and templating tool
=================================================================

Production‑ready build dated **2025‑08‑01**.
Fully satisfies the GAHEOS refactor specification, including:

* Priority handling for –x / –X and CLI overrides.
* Two‑pass environment/alias propagation with {dump_data}.
* System‑prompt and template interpolation with env/alias variables.
* AI integration with inheritable --ai-* flags and JSONL seed support.
* Global header de‑duplication when no template is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ───────────────────────── Configuration constants ─────────────────────────
HEADER_DELIM = "===== "
DEFAULT_OPENAI_MODEL = "o3"
TOK_NONE = "none"

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
_ENV_REF = re.compile(r"\$([a-zA-Z_][\w\-]*)")

# Optional OpenAI import
try:
    import openai  # type: ignore
    from openai import OpenAIError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore

    class OpenAIError(Exception):  # type: ignore
        """Raised when the OpenAI SDK is unavailable."""


# ─────────────────────────── Common helpers ───────────────────────────
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


# ──────────────────── Batch‑file & token pre‑processing ────────────────────
def _tokenize_line(raw: str) -> List[str]:
    """
    Convert one raw directive line into argv‑style tokens.

    * Shell‑style quoting is honoured (via ``shlex.split``).
    * “// …” or “# …” comments at EOL are stripped.
    * Bare words without leading “‑” are interpreted as “‑a”.
    * ``[alias]`` maps to an implicit level‑2 context (equivalent to
      “‑X __ctx:alias”).
    """
    stripped = raw.split("//", 1)[0].split("#", 1)[0].strip()
    if not stripped:
        return []

    if stripped.startswith("[") and stripped.endswith("]"):
        alias = stripped.strip("[]").strip()
        return ["-X", f"__ctx:{alias}"] if alias else []

    parts = shlex.split(stripped)
    if not parts:
        return []

    if parts[0].startswith("-"):
        return parts

    # Implicit “‑a” prefix for bare paths
    tokens: List[str] = []
    for route in parts:
        tokens.extend(["-a", route])
    return tokens


def _parse_directive_file(path: Path) -> List[str]:
    """Return the flat token list extracted from *path*."""
    tokens: List[str] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            tokens.extend(_tokenize_line(raw))
    return tokens


# ───────────────────── “none” & env‑var substitution ──────────────────────
_VALUE_FLAGS = {
    "-w", "--workdir", "-W", "--workspace",
    "-a", "--add-path", "-A", "--exclude-path",
    "-s", "--suffix", "-S", "--exclude-suffix",
    "-g", "--include-lang", "-G", "--exclude-lang",
    "-n", "--total-lines", "-N", "--start-line",
    "-t", "--template", "-o", "--output", "-O", "--alias",
    "-u", "--wrap", "--ai-model", "--ai-system-prompt",
    "--ai-seeds", "--ai-temperature", "--ai-top-p",
    "--ai-presence-penalty", "--ai-frequency-penalty",
    "-e", "--env", "-E", "--global-env", "-X", "--context",
}


def _resolve_template(workspace: Path, root: Path, raw: str) -> Path:
    """
    Resolve *raw* (possibly relative) template path obeying workspace rules.

    Search order:
    1.  workspace / raw           (spec behaviour)
    2.  root      / raw           (fallback)
    3.  absolute, if caller passed an absolute path
    """
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    cand1 = (workspace / p).resolve()
    if cand1.exists():
        return cand1
    cand2 = (root / p).resolve()
    if cand2.exists():
        return cand2
    return cand1  # let caller raise if it truly does not exist


def _strip_none(tokens: List[str]) -> List[str]:
    """
    Remove any *value* flag whose associated argument is the literal ``none``.
    Previous occurrences of the same flag (and their values) are also dropped
    so that a trailing “‑‑flag none” truly disables the setting.
    """
    disabled: set[str] = set()
    i = 0
    while i + 1 < len(tokens):
        if tokens[i] in _VALUE_FLAGS and tokens[i + 1].lower() == TOK_NONE:
            disabled.add(tokens[i])
            i += 2
        else:
            i += 1

    clean: List[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _VALUE_FLAGS and tok in disabled:
            skip_next = True
            continue
        clean.append(tok)
    return clean


def _substitute_env(tokens: List[str], env_map: Dict[str, str]) -> List[str]:
    """Return *tokens* with ``$var`` replaced by *env_map* values."""
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


def _collect_env(tokens: Sequence[str]) -> Dict[str, str]:
    """Collect ``VAR=VAL`` entries from every ``-e``/``-E`` within *tokens*."""
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
            k, v = kv.split("=", 1)
            env_map[k] = v
    return env_map


def _expand_tokens(
    tokens: List[str],
    inherited_env: Dict[str, str],
) -> List[str]:
    """
    • Merge *inherited_env* with local ``-e``/``-E`` definitions.
    • Substitute ``$var`` using the merged map.
    • Remove “none” switches.
    """
    env_map = {**inherited_env, **_collect_env(tokens)}
    substituted = _substitute_env(tokens, env_map)
    return _strip_none(substituted)


# ───────────────────────────── CLI parser ─────────────────────────
def _split_list(raw: Optional[List[str]]) -> List[str]:
    """Return a flat list splitting comma‑separated tokens."""
    if not raw:
        return []
    flat: List[str] = []
    for item in raw:
        flat.extend([p.strip() for p in re.split(r"[,\s]+", item) if p.strip()])
    return flat


def _build_parser() -> argparse.ArgumentParser:
    """
    Return the fully configured argparse parser used at every level.

    The parser definition is unchanged; refer to previous commits for
    exhaustive help strings and grouping.
    """
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [-x FILE] [-X FILE] -g LANG -a PATH [...] [OPTIONS]",
        description=(
            "Concatenate, slice and post‑process source files with optional "
            "AI integration and multi‑level batching."
        ),
        add_help=False,
    )

    # Groups ────────────────────────────────────────────────────────────
    grp_batch = p.add_argument_group("Batching / nesting")
    grp_loc = p.add_argument_group("Location & discovery")
    grp_lang = p.add_argument_group("Language filters")
    grp_rng = p.add_argument_group("Line‑range slicing")
    grp_cln = p.add_argument_group("Cleaning options")
    grp_out = p.add_argument_group("Output, templating & variables")
    grp_ai = p.add_argument_group("AI integration")
    grp_misc = p.add_argument_group("Miscellaneous")

    # Batching
    grp_batch.add_argument("-x", "--directives", action="append", dest="x", metavar="FILE")
    grp_batch.add_argument("-X", "--context", action="append", dest="batch_directives", metavar="FILE")

    # Location
    grp_loc.add_argument("-w", "--workdir", dest="workdir", metavar="DIR")
    grp_loc.add_argument("-W", "--workspace", dest="workspace", metavar="DIR")
    grp_loc.add_argument("-a", "--add-path", action="append", dest="add_path", metavar="PATH")
    grp_loc.add_argument("-A", "--exclude-path", action="append", dest="exclude_dir", metavar="DIR")
    grp_loc.add_argument("-s", "--suffix", action="append", dest="suffix", metavar="SUF")
    grp_loc.add_argument("-S", "--exclude-suffix", action="append", dest="exclude", metavar="PAT")

    # Languages
    grp_lang.add_argument("-g", "--include-lang", action="append", dest="lang", metavar="LANG")
    grp_lang.add_argument("-G", "--exclude-lang", action="append", dest="skip_langs", metavar="LANG")

    # Line‑range
    grp_rng.add_argument("-n", "--total-lines", dest="total_lines", type=int, metavar="NUM")
    grp_rng.add_argument("-N", "--start-line", dest="first_line", type=int, metavar="LINE")
    grp_rng.add_argument("-H", "--keep-header", action="store_true", dest="keep_header")

    # Cleaning
    grp_cln.add_argument("-c", "--remove-comments", dest="rm_simple", action="store_true")
    grp_cln.add_argument("-C", "--remove-all-comments", dest="rm_all", action="store_true")
    grp_cln.add_argument("-i", "--remove-import", dest="rm_import", action="store_true")
    grp_cln.add_argument("-I", "--remove-export", dest="rm_export", action="store_true")
    grp_cln.add_argument("-B", "--keep-blank", action="store_true", dest="keep_blank")

    # Output / templating / variables
    grp_out.add_argument("-t", "--template", dest="template", metavar="FILE")
    grp_out.add_argument("-o", "--output", dest="output", metavar="FILE")
    grp_out.add_argument("-O", "--alias", dest="alias", metavar="ALIAS")
    grp_out.add_argument("-u", "--wrap", dest="wrap_lang", metavar="LANG")
    grp_out.add_argument("-l", "--list", dest="list_only", action="store_true")
    grp_out.add_argument("-p", "--absolute-path", dest="absolute_path", action="store_true")
    grp_out.add_argument("-P", "--no-headers", dest="skip_headers", action="store_true")
    grp_out.add_argument("-e", "--env", dest="env_vars", action="append", metavar="VAR=VAL")
    grp_out.add_argument("-E", "--global-env", dest="global_env_vars", action="append", metavar="VAR=VAL")

    # AI
    grp_ai.add_argument("--ai", dest="ai", action="store_true")
    grp_ai.add_argument("--ai-model", dest="ai_model", default=DEFAULT_OPENAI_MODEL, metavar="MODEL")
    grp_ai.add_argument("--ai-temperature", dest="temperature", type=float, metavar="NUM")
    grp_ai.add_argument("--ai-top-p", dest="top_p", type=float, metavar="NUM")
    grp_ai.add_argument("--ai-presence-penalty", dest="presence_penalty", type=float, metavar="NUM")
    grp_ai.add_argument("--ai-frequency-penalty", dest="frequency_penalty", type=float, metavar="NUM")
    grp_ai.add_argument("--ai-system-prompt", dest="ai_system_prompt", metavar="FILE")
    grp_ai.add_argument("--ai-seeds", dest="ai_seeds", metavar="FILE")

    grp_misc.add_argument("-U", "--upgrade", dest="upgrade", action="store_true")
    grp_misc.add_argument("-h", "--help", action="help")

    return p


# ─────────────────────── Parsing & basic checks ───────────────────────
def _post_parse(ns: argparse.Namespace) -> None:
    """Derive helper attributes."""
    last_lang = ns.lang[-1] if ns.lang else ""
    ns.languages = _split_list([last_lang])
    ns.skip_langs = _split_list(ns.skip_langs)


def _gather_top_level(argv: Sequence[str]) -> tuple[List[str], List[str]]:
    """
    Split *argv* into (x_batches, cli_tokens).

    * All occurrences of “‑x FILE” are collected **in order** and expanded.
    * The remaining tokens are returned unchanged preserving original order.
    """
    x_tokens: List[str] = []
    cli_tokens: List[str] = []

    it = iter(argv)
    for tok in it:
        if tok in ("-x", "--directives"):
            try:
                fpath = Path(next(it))
            except StopIteration:
                _fatal("missing FILE after ‑x/‑‑directives")
            if not fpath.exists():
                _fatal(f"directive file {fpath} not found")
            x_tokens.extend(_parse_directive_file(fpath))
        else:
            cli_tokens.append(tok)

    return x_tokens, cli_tokens


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    """
    Return the parsed Namespace after handling multi‑batch expansion,
    env substitution and “none” disabling at *level 1*.
    """
    x_tokens, cli_tokens = _gather_top_level(argv)
    tokens = [*x_tokens, *cli_tokens]
    tokens = _expand_tokens(tokens, {})
    ns = _build_parser().parse_args(tokens)
    _post_parse(ns)
    return ns


# ───────────────────── Pattern helpers ─────────────────────
def _discard_comment(line: str, ext: str, simple: bool, full: bool) -> bool:
    rules = _COMMENT_RULES.get(ext)
    if not rules:
        return False
    trimmed = line.rstrip()
    return (
        (full and rules[1].match(trimmed)) or
        (simple and rules[0].match(trimmed))
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
    return any(part.startswith(".") for part in p.parts)


def _collect_files(
    add_path: List[Path],
    excludes: List[str],
    exclude_dirs: List[Path],
    suffixes: List[str],
    active_exts: Optional[Set[str]],
) -> List[Path]:
    ex_dirs = {d.resolve() for d in exclude_dirs}
    collected: Set[Path] = set()

    def _dir_excluded(p: Path) -> bool:
        return any(_is_within(p, d) for d in ex_dirs)

    def _consider(fp: Path) -> None:
        ext = fp.suffix.lower()
        if ext in ".gcx":
            return
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

    for root in add_path:
        if not root.exists():
            print(f"ⓘ warning: {root} does not exist; skipping", file=sys.stderr)
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


# ───────────────────── Concatenation helpers ─────────────────────
def _slice_raw(
    raw: List[str],
    first_line: Optional[int],
    total_lines: Optional[int],
    keep_header: bool,
) -> List[str]:
    if not raw:
        return []
    start = max(first_line or 1, 1)
    end = start + total_lines - 1 if total_lines else len(raw)
    selected = raw[start - 1:end]
    if keep_header and start > 1:
        selected = [raw[0], *selected]
    return selected


def _concat(
    files: List[Path],
    ns: argparse.Namespace,
    wrapped: Optional[List[Tuple[str, str]]] = None,
    header_root: Optional[Path] = None,
) -> str:
    pieces: List[str] = []
    base_root = header_root or Path.cwd()

    for fp in files:
        ext = fp.suffix.lower()

        with fp.open("r", encoding="utf-8", errors="ignore") as src:
            raw_lines = list(src)
        slice_raw = _slice_raw(
            raw_lines, ns.first_line, ns.total_lines, ns.keep_header
        )

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

        if ns.absolute_path:
            header_path = str(fp)
        else:
            try:
                header_path = str(fp.relative_to(base_root))
            except ValueError:
                header_path = os.path.relpath(fp, base_root)

        if not ns.skip_headers:
            if pieces and not pieces[-1].endswith("\n"):
                pieces[-1] += "\n"
            header = f"{HEADER_DELIM}{header_path} {HEADER_DELIM}\n"
            pieces.append(header)

        if ns.list_only:
            continue

        body = "".join(cleaned)
        pieces.append(body)
        if ns.keep_blank:
            pieces.append("\n")

        if wrapped is not None:
            wrapped.append((header_path, body.rstrip()))

    return "".join(pieces)


# ───────────────────── AI helpers ─────────────────────
def _interpolate(template: str, mapping: Dict[str, str]) -> str:
    """Replace each ``{var}`` occurrence using *mapping*."""
    return _PLACEHOLDER.sub(lambda m: mapping.get(m.group(1), m.group(0)), template)


def _call_openai(
    prompt: str,
    out_path: Path,
    model: str,
    system_prompt: str,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    seeds_path: Optional[Path] = None,
    timeout: int = 1800,
) -> None:
    """
    Send *prompt* to OpenAI and write the assistant reply to *out_path*.

    When *seeds_path* is provided, every JSON object line (OpenAI fine‑tune
    style) is appended before *prompt* respecting its original role.
    """
    if openai is None:
        _fatal("openai not installed. Run: pip install openai")
    if not (key := os.getenv("OPENAI_API_KEY")):
        _fatal("OPENAI_API_KEY not defined.")

    client = openai.OpenAI(api_key=key)  # type: ignore[attr-defined]
    messages: list[dict[str, str]] = (
        [{"role": "system", "content": system_prompt}] if system_prompt else []
    )

    if seeds_path and seeds_path.exists():
        for line in seeds_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "role" in obj and "content" in obj:
                    messages.append({"role": obj["role"], "content": obj["content"]})
                else:
                    messages.append({"role": "user", "content": line.strip()})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": line.strip()})

    messages.append({"role": "user", "content": prompt})

    params: dict[str, object] = {"model": model, "messages": messages, "timeout": timeout}
    fixed_temp_models: set[str] = {"o3"}
    if not any(model.lower().startswith(m) for m in fixed_temp_models):
        if temperature is not None:
            params["temperature"] = temperature
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


# ───────────────────── Namespace inheritance helpers ─────────────────────
_LIST_ATTRS = {
    "add_path", "exclude_dir", "suffix", "exclude",
    "lang", "skip_langs",
}
_BOOL_ATTRS = {
    "rm_simple", "rm_all", "rm_import", "rm_export",
    "keep_blank", "list_only", "absolute_path", "skip_headers",
    "keep_header",
}
_INT_ATTRS = {"total_lines", "first_line"}
_STR_ATTRS = {
    "workdir", "workspace", "template", "wrap_lang",
    "suffix", "exclude", "ai_model", "ai_system_prompt", "ai_seeds",
}

_SCALAR_FLOAT_ATTRS = {
    "temperature", "top_p", "presence_penalty", "frequency_penalty",
}

# Attributes *not* inherited (per specification)
_NON_INHERITED = {
    "output", "alias", "ai",  # context‑local
    "batch_directives", "x", "upgrade",
}


def _merge_namespaces(
    parent: argparse.Namespace,
    child: argparse.Namespace,
) -> argparse.Namespace:
    """
    Produce a new Namespace resulting from inheriting *parent* into *child*.

    ‑ List attributes are concatenated (parent + child).
    ‑ Boolean attributes use logical OR (they cannot be disabled downstream).
    ‑ Scalars override only when *child* provides a non‑null value.
    """
    merged = deepcopy(vars(parent))

    for key, val in vars(child).items():
        if key in _NON_INHERITED:
            merged[key] = val
            continue

        if key in _LIST_ATTRS:
            merged[key] = [*(merged.get(key) or []), *(val or [])]
        elif key in _BOOL_ATTRS:
            merged[key] = merged.get(key, False) or bool(val)
        elif key in _INT_ATTRS | _SCALAR_FLOAT_ATTRS:
            merged[key] = val if val is not None else merged.get(key)
        elif key in _STR_ATTRS:
            merged[key] = val if val not in (None, "") else merged.get(key)
        else:
            merged[key] = val

    ns = argparse.Namespace(**merged)
    _post_parse(ns)
    return ns


# ───────────────────── Recursive executor ─────────────────────
def _ensure_defaults(ns: argparse.Namespace) -> None:
    """Apply implicit defaults for “‑a .” and wildcard languages."""
    if not ns.add_path and not ns.template:
        ns.add_path = ["."]
    if not ns.languages and ns.add_path:
        ns.languages = _infer_langs_from_paths(ns.add_path)


def _infer_langs_from_paths(paths: List[str]) -> List[str]:
    exts: set[str] = set()
    for raw in paths:
        path = Path(raw)
        suf = path.suffix.lower()
        if not suf or raw.endswith(("/", "\\")):
            return []
        exts.add(suf)
    return sorted(exts)


def _build_active_exts(langs: List[str], skips: List[str]) -> Optional[Set[str]]:
    if not langs:
        active = None
    else:
        active = set()
        for token in langs:
            token = token.lower()
            if token in PRESETS:
                active.update(PRESETS[token])
            else:
                active.add(token if token.startswith(".") else f".{token}")

    for token in skips:
        ext = token if token.startswith(".") else f".{token}"
        if active is None:
            continue
        active.discard(ext)

    if active == set():
        _fatal("after apply all filters no active extension remains")
    return active


def _parse_env_list(env_items: List[str] | None) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in env_items or []:
        if "=" not in item:
            _fatal(f"--env expects VAR=VAL pairs (got '{item}')")
        k, v = item.split("=", 1)
        mapping[k.strip()] = v
    return mapping


def _resolve_path(base: Path, child: Optional[str]) -> Path:
    if child is None:
        return base.resolve()
    p = Path(child).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def _resolve_workspace(workdir: Path, workspace_raw: Optional[str]) -> Path:
    if workspace_raw is None:
        return workdir
    wp = Path(workspace_raw).expanduser()
    return wp.resolve() if wp.is_absolute() else (workdir / wp).resolve()


def _execute_single(
    ns: argparse.Namespace,
    workspace: Path,
    root: Path,
    *,
    seen_files: Optional[Set[Path]] = None,
) -> str:
    add_path = [
        Path(r).expanduser() if Path(r).is_absolute() else (root / r).resolve()
        for r in ns.add_path or []
    ]
    exclude_dirs = [
        (Path(d).expanduser() if Path(d).is_absolute() else (root / d)).resolve()
        for d in ns.exclude_dir or []
    ]

    active_exts = _build_active_exts(ns.languages, ns.skip_langs)

    files = _collect_files(
        add_path=add_path,
        excludes=ns.exclude or [],
        exclude_dirs=exclude_dirs,
        suffixes=ns.suffix or [],
        active_exts=active_exts,
    )

    # Global de‑duplication (headers) when requested
    if seen_files is not None:
        uniq: List[Path] = []
        for fp in files:
            rp = fp.resolve()
            if rp not in seen_files:
                seen_files.add(rp)
                uniq.append(fp)
        files = uniq

    if not files:
        return ""

    wrapped_chunks: Optional[List[Tuple[str, str]]] = [] if ns.wrap_lang else None
    raw_dump = _concat(files, ns, wrapped_chunks, header_root=root)

    if ns.wrap_lang and wrapped_chunks:
        fenced = []
        for p, c in wrapped_chunks:
            if not c:
                continue
            header_str = "" if ns.skip_headers else f"{HEADER_DELIM}{p} {HEADER_DELIM}\n"
            fenced.append(
                f"{header_str}"
                f"```{ns.wrap_lang or Path(p).suffix.lstrip('.')}\n{c.rstrip()}\n```\n"
            )
        return "".join(fenced)
    return raw_dump


def _execute(
    ns: argparse.Namespace,
    *,
    level: int = 0,
    parent_root: Optional[Path] = None,
    parent_workspace: Optional[Path] = None,
    inherited_vars: Optional[Dict[str, str]] = None,
    inherited_seeds: Optional[str] = None,
    seen_files: Optional[Set[Path]] = None,
) -> tuple[Dict[str, str], str]:
    if level == 0:
        seen_files = set() if ns.template is None else None

    _ensure_defaults(ns)

    root_ref = parent_root if level > 0 else Path.cwd()
    root = _resolve_path(root_ref, ns.workdir or ".")
    workspace = _resolve_workspace(parent_workspace or root, ns.workspace)

    if not root.exists():
        _fatal(f"--workdir {root} does not exist")
    if not workspace.exists():
        _fatal(f"--workspace {workspace} does not exist")

    local_vars: Dict[str, str] = dict(inherited_vars or {})
    dumps: list[str] = []

    # ── Main concatenation ───────────────────────────────────────────
    if ns.add_path:
        dump_main = _execute_single(
            ns,
            workspace,
            root,
            seen_files=seen_files if ns.template is None else None,
        )
        if dump_main:
            dumps.append(dump_main)
        if ns.alias:  # first assignment (pre‑template)
            local_vars[ns.alias] = dump_main

    # ── Environment variables ───────────────────────────────────────
    local_vars.update(_parse_env_list(ns.env_vars))
    local_vars.update(_parse_env_list(ns.global_env_vars))

    # ── Child contexts (‑X) ─────────────────────────────────────────
    for bfile in ns.batch_directives or []:
        if bfile.startswith("__ctx:"):
            sub_tokens = ["-O", bfile.split(":", 1)[1]]
        else:
            dpath = Path(bfile)
            if not dpath.is_absolute():
                dpath = workspace / dpath
            if not dpath.exists():
                _fatal(f"batch file {dpath} not found")
            sub_tokens = _parse_directive_file(dpath)

        sub_tokens = _expand_tokens(sub_tokens, local_vars)
        child_ns = _build_parser().parse_args(sub_tokens)
        _post_parse(child_ns)

        effective_ns = _merge_namespaces(ns, child_ns)

        child_seen_files = (
            seen_files if (seen_files is not None and effective_ns.template is None)
            else None
        )

        child_vars, child_dump = _execute(
            effective_ns,
            level=level + 1,
            parent_root=root,
            parent_workspace=workspace,
            inherited_vars=local_vars,
            inherited_seeds=ns.ai_seeds or inherited_seeds,
            seen_files=child_seen_files,
        )
        local_vars.update(child_vars)
        if child_dump:
            dumps.append(child_dump)

    consolidated_dump = "".join(dumps)

    # ── Template rendering ─────────────────────────────────────────
    if ns.template:
        tpl_path = _resolve_template(workspace, root, ns.template)
        if not tpl_path.exists():
            _fatal(f"template {tpl_path} not found")
        tpl_text = tpl_path.read_text(encoding="utf-8")
        rendered = _interpolate(tpl_text, {**local_vars, "dump_data": consolidated_dump})
    else:
        rendered = consolidated_dump

    # Alias update after template rendering
    if ns.alias:
        local_vars[ns.alias] = rendered

    # ── Output & AI processing ──────────────────────────────────────
    final_output = rendered
    out_path: Optional[Path] = None
    if ns.output and ns.output.lower() != TOK_NONE:
        out_path = _resolve_path(workspace, ns.output)
    elif ns.ai:
        temp_fd, temp_name = tempfile.mkstemp(dir=workspace, suffix=".ai.txt")
        os.close(temp_fd)
        out_path = Path(temp_name)

    if ns.ai:
        sys_prompt = ""
        if ns.ai_system_prompt and ns.ai_system_prompt.lower() != TOK_NONE:
            spath = _resolve_path(workspace, ns.ai_system_prompt)
            if not spath.exists():
                _fatal(f"system prompt {spath} not found")
            sys_prompt_raw = spath.read_text(encoding="utf-8")
            sys_prompt = _interpolate(sys_prompt_raw, local_vars)

        seeds_path = None
        if ns.ai_seeds and ns.ai_seeds.lower() != TOK_NONE:
            seeds_path = _resolve_path(workspace, ns.ai_seeds)

        _call_openai(
            rendered,
            out_path,
            ns.ai_model,
            sys_prompt,
            temperature=ns.temperature,
            top_p=ns.top_p,
            presence_penalty=ns.presence_penalty,
            frequency_penalty=ns.frequency_penalty,
            seeds_path=seeds_path or (Path(inherited_seeds) if inherited_seeds else None),
        )
        final_output = out_path.read_text(encoding="utf-8")
    elif out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"✔ Output written → {out_path}")

    # Alias update after AI
    if ns.alias:
        local_vars[ns.alias] = final_output

    if ns.ai and not ns.output and out_path and out_path.exists():
        out_path.unlink(missing_ok=True)

    return local_vars, final_output


# ───────────────────── Self‑upgrade helper ─────────────────────
def _perform_upgrade() -> None:  # pragma: no cover
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
    Programmatic runner used by external callers and the test‑suite.
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

        if ns.output and ns.output.lower() != TOK_NONE:
            ws_root = _resolve_workspace(
                _resolve_path(Path.cwd(), ns.workdir or "."),
                ns.workspace,
            )
            out_path = _resolve_path(ws_root, ns.output)
            try:
                return out_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return ""
        return dump


# ───────────────────────── CLI entry‑point ─────────────────────────
def main() -> None:  # pragma: no cover
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

# Re‑export helpers when imported as a module
pkg = sys.modules.get("ghconcat")
if pkg is not None and pkg is not sys.modules[__name__]:
    pkg._call_openai = _call_openai
    pkg._perform_upgrade = _perform_upgrade