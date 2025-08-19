# src/ghconcat/cli.py
"""
ghconcat – hierarchical, language-agnostic concatenation & templating tool.

Gaheos – https://gaheos.com
Copyright (c) 2025 GAHEOS S.A.
Copyright (c) 2025 Leonardo Gavidia Guerra <leo@gaheos.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""


import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, NoReturn
import logging
import ssl

from ghconcat.parser import _build_parser
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.processing.envctx import EnvContext
from ghconcat.parsing.directives import DirNode, DirectiveParser
from ghconcat.parsing.flags import VALUE_FLAGS as _VALUE_FLAGS
from ghconcat.parsing.tokenize import inject_positional_add_paths
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.comment_rules import COMMENT_RULES

from ghconcat.runtime.container import EngineBuilder

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ghconcat")


HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"

_LINE1_RE: re.Pattern[str] = re.compile(r"^\s*#\s*line\s*1\d*\s*$")
_WORKSPACES_SEEN: set[Path] = set()

_LINE_OPS = LineProcessingService(
    comment_rules=COMMENT_RULES,
    line1_re=_LINE1_RE,
    logger=logger,
)
_INTERPOLATOR = StringInterpolator()
_TEXT_TRANSFORMER = TextTransformer(logger=logger, regex_delim="/")
_ENV_CONTEXT = EnvContext(logger=logger)

_INT_ATTRS: Set[str] = {
    "total_lines", "first_line",
    "url_scrape_depth",
    "ai_max_tokens",
}

_LIST_ATTRS: Set[str] = {
    "add_path", "exclude_path", "suffix", "exclude_suf",
    "hdr_flags", "path_flags", "blank_flags", "first_flags",
    "urls", "url_scrape", "git_path", "git_exclude",
    "replace_rules", "preserve_rules",
}

_BOOL_ATTRS: Set[str] = {
    "rm_simple", "rm_all", "rm_import", "rm_export",
    "keep_blank", "list_only", "absolute_path", "skip_headers",
    "keep_header", "disable_url_domain_only", "preserve_cache"
}

_STR_ATTRS: Set[str] = {
    "workdir", "workspace", "template", "wrap_lang", "child_template",
    "ai_model", "ai_system_prompt", "ai_seeds",
    "ai_reasoning_effort",
}

_FLT_ATTRS: Set[str] = {
    "ai_temperature",
    "ai_top_p",
    "ai_presence_penalty",
    "ai_frequency_penalty",
}

_NON_INHERITED: Set[str] = {"output", "unwrap", "ai", "template"}
_GIT_CLONES: Dict[Tuple[str, str | None], Path] = {}
_RE_DELIM: str = "/"

def _ssl_ctx_for(url: str) -> Optional[ssl.SSLContext]:
    """
    Build an SSL context for *url* honoring the environment variable:

        GHCONCAT_INSECURE_TLS=1  → disables certificate verification.

    If the flag is not set or the URL is not HTTPS, returns None (default context).
    """
    if not url.lower().startswith("https"):
        return None
    if os.getenv("GHCONCAT_INSECURE_TLS") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _fatal(msg: str, code: int = 1) -> None:
    """Abort execution immediately with *msg* written to *stderr*."""
    logger.error(msg)
    sys.exit(code)


def _debug_enabled() -> bool:  # pragma: no cover
    """Utility guard to ease local debugging (`DEBUG=1`)."""
    return os.getenv("DEBUG") == "1"


def _apply_replacements(
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
) -> str:
    """Thin wrapper delegating to TextTransformer (single source of truth)."""
    return _TEXT_TRANSFORMER.apply_replacements(text, replace_specs, preserve_specs)


def _expand_tokens(tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
    """Delegate full expansion pipeline to EnvContext (single source of truth)."""
    return _ENV_CONTEXT.expand_tokens(
        tokens,
        inherited_env,
        value_flags=_VALUE_FLAGS,
        none_value=TOK_NONE,
    )


def _post_parse(ns: argparse.Namespace) -> None:
    """Normalize tri-state flags after `parse_args` has run."""
    flags = set(ns.blank_flags or [])
    ns.keep_blank = "keep" in flags or "strip" not in flags

    first = set(ns.first_flags or [])
    if "drop" in first:
        ns.keep_header = False
    else:
        ns.keep_header = "keep" in first

    hdr = set(ns.hdr_flags or [])
    ns.skip_headers = not ("show" in hdr and "hide" not in hdr)

    pathf = set(ns.path_flags or [])
    ns.absolute_path = "absolute" in pathf and "relative" not in pathf

    if ns.unwrap:
        ns.wrap_lang = None

    if getattr(ns, "no_list", False):
        ns.list_only = False


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
    """Apply comment/import/blank filtering to *lines* via LineProcessingService."""
    return _LINE_OPS.clean_lines(
        lines,
        ext,
        rm_simple=rm_simple,
        rm_all=rm_all,
        rm_imp=rm_imp,
        rm_exp=rm_exp,
        keep_blank=keep_blank,
    )


def _interpolate(tpl: str, mapping: Dict[str, str]) -> str:
    """Single-brace interpolation preserving legacy rules."""
    return _INTERPOLATOR.interpolate(tpl, mapping)


def _call_openai(
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
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
) -> None:
    """
    Send *prompt* to OpenAI unless GHCONCAT_DISABLE_AI=1 – in that case write
    “AI-DISABLED”.

    Notes
    -----
    • Keeps 1:1 compatibility with legacy behavior for the test-suite.
    """
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return

    if not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return

    try:
        from ghconcat.ai.ai_client import OpenAIClient
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")
        return

    client = OpenAIClient(logger=logger)

    try:
        out_path.write_text(client.generate_chat_completion(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            presence_penalty=presence_pen,
            frequency_penalty=freq_pen,
            seeds_path=seeds_path,
            timeout=timeout,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


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


def _parse_env_items(items: Optional[List[str]]) -> Dict[str, str]:
    """Parse VAR=VAL items with strict validation (fatal on malformed)."""
    return _ENV_CONTEXT.parse_items(items, on_error=lambda m: _fatal(m))


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
    Compatibility wrapper: delegates to the ExecutionEngine composed by
    EngineBuilder. Behavior remains strictly identical to the legacy
    implementation.  All helper functions, sets and constants from this
    module are injected to preserve semantics.
    """

    # Use the ghconcat._call_openai bridge (allowing tests to patch it)
    _call_fn = (_call_openai if "ghconcat" not in sys.modules
                else getattr(sys.modules["ghconcat"], "_call_openai"))

    builder = EngineBuilder(
        logger=logger,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,  # set is reset in GhConcat.run()
        clones_cache=_GIT_CLONES,
        workspaces_seen=_WORKSPACES_SEEN,
        ssl_ctx_provider=_ssl_ctx_for,
        parser_factory=_build_parser,
        post_parse=_post_parse,
        merge_ns=_merge_ns,
        expand_tokens=_expand_tokens,
        parse_env_items=_parse_env_items,
        interpolate=_INTERPOLATOR.interpolate,
        apply_replacements=_apply_replacements,
        slice_lines=_LINE_OPS.slice_lines,
        clean_lines=_LINE_OPS.clean_lines,
        fatal=lambda msg: _fatal(msg),
    )
    engine = builder.build(call_openai=_call_fn)

    return engine.execute_node(
        node,
        ns_parent,
        level=level,
        parent_root=parent_root,
        parent_workspace=parent_workspace,
        inherited_vars=inherited_vars,
        gh_dump=gh_dump,
    )


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
        logger.info(f"✔ Updated → {dest}")
    except Exception as exc:  # noqa: BLE001
        _fatal(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


def _purge_caches() -> None:
    """
    Remove every «.ghconcat_*cache» directory observed during execution
    (git + URL scraper), unless the session requested to preserve them.
    """
    patterns = (".ghconcat_gitcache", ".ghconcat_urlcache")
    for ws in _WORKSPACES_SEEN:
        for pat in patterns:
            tgt = ws / pat
            if tgt.exists():
                try:
                    shutil.rmtree(tgt, ignore_errors=True)
                    logger.info(f"🗑  cache removed → {tgt}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"⚠  could not delete {tgt}: {exc}")


class GhConcat:
    """
    Programmatic entry-point.

    * When an explicit «-o» is present the file is written **and** also
      returned as a *str* for convenience.
    * Otherwise the in-memory dump is returned.
    """

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """
        Execute ghconcat over *argv* and return the concatenation result.

        Each «-x FILE» starts a completely isolated directive tree.
        Bare paths passed at the CLI level are implicitly converted into
        “-a PATH” arguments.
        """
        global _SEEN_FILES
        _SEEN_FILES = set()  # full reset per public call
        _GIT_CLONES.clear()

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
                units.append((fpath, inject_positional_add_paths(cli_remainder)))
                cli_remainder = []
            else:
                cli_remainder.append(tok)

        if not units:
            units.append((None, inject_positional_add_paths(cli_remainder)))
        elif cli_remainder:
            last_path, last_cli = units[-1]
            units[-1] = (last_path, last_cli + inject_positional_add_paths(cli_remainder))

        outputs: List[str] = []
        dparser = DirectiveParser(logger=logger)  # OO parser

        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()  # dedup scope per unit

            if directive_path:
                root = dparser.parse(directive_path)
                root.tokens.extend(extra_cli)
            else:
                root = DirNode()
                root.tokens.extend(extra_cli)

            if "--upgrade" in root.tokens:
                (_perform_upgrade if "ghconcat" not in sys.modules
                 else getattr(sys.modules["ghconcat"], "_perform_upgrade"))()

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if "--preserve-cache" not in argv:
            _purge_caches()

        return "".join(outputs)


def main() -> NoReturn:
    try:
        GhConcat.run(sys.argv[1:])
        raise SystemExit(0)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        if os.getenv("DEBUG") == "1":
            raise
        logger.error("Unexpected error: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()