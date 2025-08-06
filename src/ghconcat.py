# !/usr/bin/env python3
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

# ───────────────────────────────  Constants  ────────────────────────────────
HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"

# Pattern used to wipe any “# line 1…” when the first line must be dropped.
_LINE1_RE: re.Pattern[str] = re.compile(r"^\s*#\s*line\s*1\d*\s*$")

# This cache is *per GhConcat.run()*; it is cleared on each public entry call.
_SEEN_FILES: set[str] = set()

_COMMENT_RULES: dict[str, Tuple[
    re.Pattern[str],  # simple comment
    re.Pattern[str],  # full‑line comment
    Optional[re.Pattern[str]],  # import‑like
    Optional[re.Pattern[str]],  # export‑like
]] = {
    ".py": (
        re.compile(r"^\s*#(?!#).*$"),
        re.compile(r"^\s*#.*$"),
        re.compile(r"^\s*(?:import\b|from\b.+?\bimport\b)"),
        None,
    ),
    ".dart": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*export\b"),
    ),
    ".js": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        re.compile(r"^\s*import\b"),
        re.compile(r"^\s*(?:export\b|module\.exports\b)"),
    ),
    ".go": (
        re.compile(r"^\s*//(?!/).*$"),
        re.compile(r"^\s*(?://.*|/\*.*\*/\s*)$"),
        None,
        None,
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

_RE_BLANK: re.Pattern[str] = re.compile(r"^\s*$")
_PLACEHOLDER: re.Pattern[str] = re.compile(r"\{([a-zA-Z_][\w\-]*)\}")
_ENV_REF: re.Pattern[str] = re.compile(r"\$([a-zA-Z_][\w\-]*)")

# Optional OpenAI import (lazy)
try:
    import openai  # type: ignore
    from openai import OpenAIError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    openai = None  # type: ignore


    class OpenAIError(Exception):  # type: ignore
        """Raised when the OpenAI SDK is unavailable."""


# ───────────────────────────────  Data classes  ─────────────────────────────
class DirNode:
    """
    Simple tree container representing a “[context]” block inside a
    directive file.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name: Optional[str] = name
        self.tokens: List[str] = []
        self.children: List["DirNode"] = []


# ─────────────────────────────  Aux helpers  ────────────────────────────────
def _fatal(msg: str, code: int = 1) -> None:
    """Abort execution immediately with *msg* written to *stderr*."""
    print(msg, file=sys.stderr)
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


# ───────────────────────  Directive‑file parsing  ───────────────────────────
def _tokenize_directive_line(raw: str) -> List[str]:
    """
    Split *raw* (a single line from the directive file) into CLI‑style tokens,
    honouring `//`, `#` and `;` as inline‑comment delimiters.

    If the very first token does **not** start with “‑”, the whole line is
    treated as a list of paths and expanded into multiple “‑a PATH”.
    """
    stripped = (
        raw.split("//", 1)[0]
        .split("#", 1)[0]
        .split(";", 1)[0]
        .strip()
    )
    if not stripped:
        return []

    parts = shlex.split(stripped)
    if not parts:
        return []

    if not parts[0].startswith("-"):
        tokens: List[str] = []
        for pth in parts:
            tokens.extend(["-a", pth])
        return tokens
    return parts


def _parse_directive_file(path: Path) -> DirNode:
    """
    Build a `DirNode` tree out of the *path* directive file.
    """
    root = DirNode()
    current = root

    with path.open("r", encoding="utf-8") as fp:
        for raw in fp:
            stripped = raw.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                ctx_name = stripped.strip("[]").strip()
                node = DirNode(ctx_name)
                root.children.append(node)
                current = node
                continue

            line_toks = _tokenize_directive_line(raw)
            if line_toks:
                current.tokens.extend(line_toks)
    return root


# ─────────────────────── “none” handling & env substitution  ────────────────
_VALUE_FLAGS: Set[str] = {
    "-w", "--workdir", "-W", "--workspace",
    "-a", "--add-path", "-A", "--exclude-path",
    "-s", "--suffix", "-S", "--exclude-suffix",
    "-n", "--total-lines", "-N", "--start-line",
    "-t", "--template", "-o", "--output",
    "-u", "--wrap", "--ai-model", "--ai-system-prompt",
    "--ai-seeds", "--ai-temperature", "--ai-top-p",
    "--ai-presence-penalty", "--ai-frequency-penalty",
    "-e", "--env", "-E", "--global-env",
}


def _strip_none(tokens: List[str]) -> List[str]:
    """
    Remove *both* a flag and its value when the value is literally “none”.
    """
    disabled: set[str] = set()
    i = 0
    while i + 1 < len(tokens):
        if tokens[i] in _VALUE_FLAGS and tokens[i + 1].lower() == TOK_NONE:
            disabled.add(tokens[i])
            i += 2
        else:
            i += 1

    cleaned: List[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _VALUE_FLAGS and tok in disabled:
            skip_next = True
            continue
        cleaned.append(tok)
    return cleaned


def _substitute_env(tokens: List[str], env_map: Dict[str, str]) -> List[str]:
    """
    Replace every «$VAR» occurrence with its value from *env_map*.
    Missing variables are expanded into an empty string.
    """
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


def _collect_env_from_tokens(tokens: Sequence[str]) -> Dict[str, str]:
    """
    Scan *tokens* and gather every definition that follows “‑e/‑E”.
    """
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
            key, val = kv.split("=", 1)
            env_map[key] = val
    return env_map


def _expand_tokens(tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
    """
    Perform a full expansion pass:

    1. Gather all env definitions on the line.
    2. Substitute “$VAR”.
    3. Strip any “none”‑disabled flags.
    """
    env_all = {**inherited_env, **_collect_env_from_tokens(tokens)}
    return _strip_none(_substitute_env(tokens, env_all))


def _refresh_env_values(env_map: Dict[str, str]) -> None:
    """
    Re‑evaluate *env_map* until no “$VAR” references remain.

    This is performed after *raw‑concat*, *template* and *AI* stages, because
    those stages might add new variables that are referenced by others.
    """
    changed = True
    while changed:
        changed = False
        for key, val in list(env_map.items()):
            new_val = _ENV_REF.sub(lambda m: env_map.get(m.group(1), ""), val)
            if new_val != val:
                env_map[key] = new_val
                changed = True


# ─────────────────────── argparse builder (no “‑X”)  ────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    """
    Build and return an `argparse.ArgumentParser` suitable for a single
    context block.
    """
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [‑x FILE] … [OPTIONS]",
        add_help=False,
    )

    # ── groups
    g_loc = p.add_argument_group("Discovery")
    g_rng = p.add_argument_group("Line slicing")
    g_cln = p.add_argument_group("Cleaning")
    g_tpl = p.add_argument_group("Template & output")
    g_ai = p.add_argument_group("AI integration")
    g_misc = p.add_argument_group("Misc")

    # ── discovery
    g_loc.add_argument("-w", "--workdir", dest="workdir", metavar="DIR")
    g_loc.add_argument("-W", "--workspace", dest="workspace", metavar="DIR")
    g_loc.add_argument("-a", "--add-path", action="append", dest="add_path", metavar="PATH")
    g_loc.add_argument("-A", "--exclude-path", action="append", dest="exclude_path", metavar="DIR")
    g_loc.add_argument("-s", "--suffix", action="append", dest="suffix", metavar="SUF")
    g_loc.add_argument("-S", "--exclude-suffix", action="append", dest="exclude_suf", metavar="SUF")

    # ── line range
    g_rng.add_argument("-n", "--total-lines", dest="total_lines", type=int, metavar="NUM")
    g_rng.add_argument("-N", "--start-line", dest="first_line", type=int, metavar="LINE")
    g_rng.add_argument("-m", "--keep-first-line", dest="first_flags",
                       action="append_const", const="keep")
    g_rng.add_argument("-M", "--no-first-line", dest="first_flags",
                       action="append_const", const="drop")

    # ── cleaning
    g_cln.add_argument("-c", "--remove-comments", dest="rm_simple", action="store_true")
    g_cln.add_argument("-C", "--remove-all-comments", dest="rm_all", action="store_true")
    g_cln.add_argument("-i", "--remove-import", dest="rm_import", action="store_true")
    g_cln.add_argument("-I", "--remove-export", dest="rm_export", action="store_true")
    g_cln.add_argument("-B", "--keep-blank", dest="blank_flags",
                       action="append_const", const="keep")
    g_cln.add_argument("-b", "--strip-blank", dest="blank_flags",
                       action="append_const", const="strip")

    # ── template & output
    g_tpl.add_argument("-t", "--template", dest="template", metavar="FILE")
    g_tpl.add_argument("-o", "--output", dest="output", metavar="FILE")
    g_tpl.add_argument("-u", "--wrap", dest="wrap_lang", metavar="LANG")
    g_tpl.add_argument("-U", "--no-wrap", dest="unwrap", action="store_true")
    g_tpl.add_argument("-h", "--header", dest="hdr_flags",
                       action="append_const", const="show")
    g_tpl.add_argument("-H", "--no-headers", dest="hdr_flags",
                       action="append_const", const="hide")
    g_tpl.add_argument("-r", "--relative-path", dest="path_flags",
                       action="append_const", const="relative")
    g_tpl.add_argument("-R", "--absolute-path", dest="path_flags",
                       action="append_const", const="absolute")
    g_tpl.add_argument("-l", "--list", dest="list_only", action="store_true")
    g_tpl.add_argument("-e", "--env", dest="env_vars", action="append", metavar="VAR=VAL")
    g_tpl.add_argument("-E", "--global-env", dest="global_env", action="append", metavar="VAR=VAL")

    # ── AI
    g_ai.add_argument("--ai", action="store_true")
    g_ai.add_argument("--ai-model", default=DEFAULT_OPENAI_MODEL, metavar="MODEL")
    g_ai.add_argument("--ai-temperature", type=float, metavar="NUM")
    g_ai.add_argument("--ai-top-p", type=float, metavar="NUM")
    g_ai.add_argument("--ai-presence-penalty", type=float, metavar="NUM")
    g_ai.add_argument("--ai-frequency-penalty", type=float, metavar="NUM")
    g_ai.add_argument("--ai-system-prompt", metavar="FILE")
    g_ai.add_argument("--ai-seeds", metavar="FILE")

    # ── misc
    g_misc.add_argument("--upgrade", action="store_true")
    g_misc.add_argument("--help", action="help")

    return p


# ───────────────────────  Namespace post‑processing  ────────────────────────
def _post_parse(ns: argparse.Namespace) -> None:
    """
    Normalize tri‑state flags after `parse_args` has run.
    """
    # Blank‑line policy
    flags = set(ns.blank_flags or [])
    ns.keep_blank = "keep" in flags or "strip" not in flags

    # First‑line policy
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


def _gather_files(
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
) -> List[Path]:
    """
    Walk *add_path* and return every file that matches inclusion / exclusion
    rules. Explicit files always win.
    """
    collected: Set[Path] = set()

    explicit_files = [p for p in add_path if p.is_file()]
    dir_paths = [p for p in add_path if not p.is_file()]

    suffixes = [s if s.startswith(".") else f".{s}" for s in suffixes]
    exclude_suf = [s if s.startswith(".") else f".{s}" for s in exclude_suf]
    excl_set = set(exclude_suf) - set(suffixes)

    ex_dirs = {d.resolve() for d in exclude_dirs}

    def _dir_excluded(path: Path) -> bool:
        return any(_is_within(path, ex) for ex in ex_dirs)

    # Explicit files first
    for fp in explicit_files:
        collected.add(fp.resolve())

    for root in dir_paths:
        if not root.exists():
            print(f"⚠  {root} does not exist – skipped", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and not _dir_excluded(Path(dirpath, d))
            ]
            for fn in filenames:
                fp = Path(dirpath, fn)
                if _hidden(fp) or _dir_excluded(fp):
                    continue
                if suffixes and not any(fp.name.endswith(s) for s in suffixes):
                    continue
                if any(fp.name.endswith(s) for s in excl_set):
                    continue
                if fp.name.endswith((".pyc", ".pyo")):
                    continue
                collected.add(fp.resolve())

    return sorted(collected, key=str)


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
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
) -> str:
    """
    Concatenate *files* applying cleaning, headers and optional wrapping.
    """
    parts: List[str] = []
    comment_prefix = {
        ".py": "# ",
        ".js": "// ",
        ".dart": "// ",
        ".go": "// ",
        ".yml": "# ",
        ".yaml": "# ",
        ".xml": "<!-- ",
        ".csv": "# ",
    }

    for idx, fp in enumerate(files):
        ext = fp.suffix.lower()
        with fp.open("r", encoding="utf-8", errors="ignore") as fh:
            raw_lines = list(fh)

        body_lines = _clean(
            _slice(raw_lines, ns.first_line, ns.total_lines, ns.keep_header),
            ext,
            rm_simple=ns.rm_simple or ns.rm_all,
            rm_all=ns.rm_all,
            rm_imp=ns.rm_import,
            rm_exp=ns.rm_export,
            keep_blank=ns.keep_blank,
        )

        if ns.list_only:
            rel = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)
            parts.append(rel + "\n")
            continue

        if not body_lines or not "".join(body_lines).strip():
            continue

        hdr_path = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)

        # Traditional header (if “‑h”)
        if not ns.skip_headers and hdr_path not in _SEEN_FILES:
            parts.append(f"{HEADER_DELIM}{hdr_path} {HEADER_DELIM}\n")
            _SEEN_FILES.add(hdr_path)

        # Lightweight comment header (if “‑h” not requested)
        if ns.skip_headers:
            prefix = comment_prefix.get(ext, "# ")
            suffix = " -->\n" if prefix.startswith("<!--") else "\n"
            parts.append(f"{prefix}{hdr_path}{suffix}")

        body = "".join(body_lines)
        parts.append(body)

        if wrapped is not None:
            wrapped.append((hdr_path, body.rstrip()))

        if ns.keep_blank and (
                idx < len(files) - 1
                or (
                        idx == len(files) - 1
                        and ns.total_lines is None
                        and ns.first_line is None
                )
        ):
            parts.append("\n")

    return "".join(parts)


# ─────────────────────────────  AI helpers  ─────────────────────────────────
def _interpolate(tpl: str, mapping: Dict[str, str]) -> str:
    """Simple placeholder {var} → mapping[var] (missing ⇒ empty)."""
    return _PLACEHOLDER.sub(lambda m: mapping.get(m.group(1), ""), tpl)


def _call_openai(  # pragma: no cover
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
) -> None:
    """
    Send *prompt* to OpenAI unless GHCONCAT_DISABLE_AI=1 – in that case write
    “AI‑DISABLED”.
    """
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return

    if openai is None or not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return

    client = openai.OpenAI()  # type: ignore[attr-defined]

    messages = (
        [{"role": "system", "content": system_prompt}] if system_prompt else []
    )
    if seeds_path and seeds_path.exists():
        for ln in seeds_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                obj = json.loads(ln)
                if isinstance(obj, dict) and {"role", "content"} <= obj.keys():
                    messages.append(
                        {"role": obj["role"], "content": obj["content"]}
                    )
                else:
                    messages.append({"role": "user", "content": ln.strip()})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": ln.strip()})

    messages.append({"role": "user", "content": prompt})

    params: Dict[str, object] = {"model": model, "messages": messages, "timeout": timeout}
    if not model.lower().startswith("o3"):
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p
        if presence_pen is not None:
            params["presence_penalty"] = presence_pen
        if freq_pen is not None:
            params["frequency_penalty"] = freq_pen

    try:
        rsp = client.chat.completions.create(**params)  # type: ignore[arg-type]
        out_path.write_text(rsp.choices[0].message.content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


# ─────────────────────────────  Merge helpers  ──────────────────────────────
_LIST_ATTRS: Set[str] = {
    "add_path", "exclude_path", "suffix", "exclude_suf",
    "hdr_flags", "path_flags", "blank_flags", "first_flags",
}
_BOOL_ATTRS: Set[str] = {
    "rm_simple", "rm_all", "rm_import", "rm_export",
    "keep_blank", "list_only", "absolute_path", "skip_headers",
    "keep_header",
}
_INT_ATTRS: Set[str] = {"total_lines", "first_line"}
_STR_ATTRS: Set[str] = {
    "workdir", "workspace", "template", "wrap_lang",
    "ai_model", "ai_system_prompt", "ai_seeds",
}
_FLT_ATTRS: Set[str] = {
    "ai_temperature",
    "ai_top_p",
    "ai_presence_penalty",
    "ai_frequency_penalty",
}
_NON_INHERITED: Set[str] = {"output", "unwrap", "ai"}


def _merge_ns(parent: argparse.Namespace, child: argparse.Namespace) -> argparse.Namespace:
    """
    Return a **new** namespace = parent ⊕ child (child overrides, lists extend).
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

    ns = argparse.Namespace(**merged)
    _post_parse(ns)
    return ns


# ─────────────────────────────  Core executor  ──────────────────────────────
def _parse_env_items(items: Optional[List[str]]) -> Dict[str, str]:
    env_map: Dict[str, str] = {}
    for itm in items or []:
        if "=" not in itm:
            _fatal(f"--env expects VAR=VAL (got '{itm}')")
        key, val = itm.split("=", 1)
        env_map[key] = val
    return env_map


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
    Recursive executor. Returns *(vars, final_output)* for *node*.
    """
    inherited_vars = inherited_vars or {}
    tokens = _expand_tokens(node.tokens, inherited_vars)
    ns_self = _build_parser().parse_args(tokens)
    _post_parse(ns_self)
    ns_effective = _merge_ns(ns_parent, ns_self) if ns_parent else ns_self

    if level == 0:
        gh_dump = []
        _SEEN_FILES.clear()  # header de‑dup reset

    root_base = parent_root or Path.cwd()
    root = _resolve_path(root_base, ns_effective.workdir or ".")

    workspace = (
        _resolve_path(parent_workspace or root, ns_effective.workspace)
        if ns_effective.workspace
        else root
    )
    if not root.exists():
        _fatal(f"--workdir {root} not found")
    if not workspace.exists():
        _fatal(f"--workspace {workspace} not found")

    # ── env ---------------------------------------------------------------
    vars_local: Dict[str, str] = dict(inherited_vars)
    vars_local.update(_parse_env_items(ns_effective.global_env))
    vars_local.update(_parse_env_items(ns_effective.env_vars))
    ctx_name = node.name

    # ── RAW CONCAT --------------------------------------------------------
    dump_raw = ""
    if ns_effective.add_path:
        files = _gather_files(
            add_path=[
                Path(p) if Path(p).is_absolute() else (root / p).resolve()
                for p in ns_effective.add_path
            ],
            exclude_dirs=[
                Path(p) if Path(p).is_absolute() else (root / p).resolve()
                for p in ns_effective.exclude_path or []
            ],
            suffixes=_split_list(ns_effective.suffix),
            exclude_suf=_split_list(ns_effective.exclude_suf),
        )
        if files:
            wrapped: Optional[List[Tuple[str, str]]] = (
                [] if ns_effective.wrap_lang else None
            )
            dump_raw = _concat_files(files, ns_effective, header_root=root, wrapped=wrapped)
            if ns_effective.wrap_lang and wrapped:
                fenced = []
                for hp, body in wrapped:
                    hdr = (
                        ""
                        if ns_effective.skip_headers
                        else f"{HEADER_DELIM}{hp} {HEADER_DELIM}\n"
                    )
                    fenced.append(
                        f"{hdr}```{ns_effective.wrap_lang or Path(hp).suffix.lstrip('.')}\n"
                        f"{body}\n```\n"
                    )
                dump_raw = "".join(fenced)

    if ctx_name:
        vars_local[f"_r_{ctx_name}"] = dump_raw
        vars_local[ctx_name] = dump_raw
    if gh_dump is not None:
        gh_dump.append(dump_raw)

    _refresh_env_values(vars_local)  # after concat

    # ── CHILD CONTEXTS ----------------------------------------------------
    for child in node.children:
        child_vars, _ = _execute_node(
            child,
            ns_effective,
            level=level + 1,
            parent_root=root,
            parent_workspace=workspace,
            inherited_vars=vars_local,
            gh_dump=gh_dump,
        )
        vars_local.update(child_vars)

    _refresh_env_values(vars_local)  # after children

    # ── TEMPLATE ----------------------------------------------------------
    rendered = dump_raw
    if ns_effective.template:
        tpl_path = _resolve_path(workspace, ns_effective.template)
        if not tpl_path.exists():
            _fatal(f"template {tpl_path} not found")
        tpl_text = tpl_path.read_text(encoding="utf-8")
        rendered = _interpolate(
            tpl_text, {**vars_local, "ghconcat_dump": "".join(gh_dump or [])}
        )

    if ctx_name:
        vars_local[f"_t_{ctx_name}"] = rendered
        vars_local[ctx_name] = rendered

    _refresh_env_values(vars_local)  # after template

    # ── AI ----------------------------------------------------------------
    final_out = rendered
    out_path: Optional[Path] = None
    if ns_effective.output and ns_effective.output.lower() != TOK_NONE:
        out_path = _resolve_path(workspace, ns_effective.output)

    if ns_effective.ai:
        if out_path is None:
            tf = tempfile.NamedTemporaryFile(
                delete=False, dir=workspace, suffix=".ai.txt"
            )
            tf.close()
            out_path = Path(tf.name)

        sys_prompt = ""
        if (
                ns_effective.ai_system_prompt
                and ns_effective.ai_system_prompt.lower() != TOK_NONE
        ):
            spath = _resolve_path(workspace, ns_effective.ai_system_prompt)
            if not spath.exists():
                _fatal(f"system prompt {spath} not found")
            sys_prompt = _interpolate(spath.read_text(encoding="utf-8"), vars_local)

        seeds = None
        if ns_effective.ai_seeds and ns_effective.ai_seeds.lower() != TOK_NONE:
            seeds = _resolve_path(workspace, ns_effective.ai_seeds)

        # Dynamic call – eases unittest.mock patching
        if "ghconcat" in sys.modules:
            _call_openai_safe = getattr(sys.modules["ghconcat"], "_call_openai")
        else:
            _call_openai_safe = _call_openai

        _call_openai_safe(
            rendered,
            out_path,
            model=ns_effective.ai_model,
            system_prompt=sys_prompt,
            temperature=ns_effective.ai_temperature,
            top_p=ns_effective.ai_top_p,
            presence_pen=ns_effective.ai_presence_penalty,
            freq_pen=ns_effective.ai_frequency_penalty,
            seeds_path=seeds,
        )
        final_out = out_path.read_text(encoding="utf-8")

    if ctx_name:
        vars_local[f"_ia_{ctx_name}"] = final_out
        vars_local[ctx_name] = final_out

    _refresh_env_values(vars_local)  # after AI

    # ── OUTPUT ------------------------------------------------------------
    if out_path and not ns_effective.ai:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(final_out, encoding="utf-8")
        print(f"✔ Output written → {out_path}")

    # Root‑level synthetic output (if nothing else captured it)
    if level == 0 and final_out == "" and gh_dump:
        final_out = "".join(gh_dump)

    if level == 0 and gh_dump is not None:
        vars_local["ghconcat_dump"] = "".join(gh_dump)

    return vars_local, final_out


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
        print(f"✔ Updated → {dest}")
    except Exception as exc:  # noqa: BLE001
        _fatal(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


# ────────────────────────────  Public API  ──────────────────────────────────
class GhConcat:
    """
    Programmatic entry‑point.

    * When an explicit «‑o» is present the file is written **and** also
      returned as a *str* for convenience.
    * Otherwise the in‑memory dump is returned.
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute ghconcat over *argv* and return the concatenation result.

        Each «‑x FILE» starts a completely isolated directive tree.
        """
        global _SEEN_FILES
        _SEEN_FILES = set()  # full reset per public call

        # ── split by “‑x” -------------------------------------------------
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
                units.append((fpath, cli_remainder))
                cli_remainder = []
            else:
                cli_remainder.append(tok)

        if not units:
            units.append((None, cli_remainder))
        elif cli_remainder:
            units[-1] = (units[-1][0], units[-1][1] + cli_remainder)

        # ── execute each unit --------------------------------------------
        outputs: List[str] = []
        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()  # dedup scope per unit

            if directive_path:
                root = _parse_directive_file(directive_path)
                root.tokens.extend(extra_cli)
            else:
                root = DirNode()
                root.tokens.extend(extra_cli)

            # Dynamic call – eases unittest patch
            if "--upgrade" in root.tokens:
                if "ghconcat" in sys.modules:
                    _perform_upgrade_safe = getattr(sys.modules["ghconcat"], "_perform_upgrade")
                else:
                    _perform_upgrade_safe = _perform_upgrade
                _perform_upgrade_safe()

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        return "".join(outputs)


# ────────────────────────────  CLI main()  ──────────────────────────────────
def main() -> None:  # pragma: no cover
    """CLI dispatcher used by the real `ghconcat` executable."""
    try:
        result = GhConcat.run(sys.argv[1:])
        if result and not sys.stdout.isatty():
            sys.stdout.write(result)
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
