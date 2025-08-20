from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, NoReturn, Any
import logging

from ghconcat.logging.factory import DefaultLoggerFactory
from ghconcat.parsing.attr_sets import (
    _BOOL_ATTRS,
    _FLT_ATTRS,
    _INT_ATTRS,
    _LIST_ATTRS,
    _NON_INHERITED,
    _STR_ATTRS,
    _VALUE_FLAGS,
)
from ghconcat.parsing.directives import DirNode, DirectiveParser
from ghconcat.parsing.tokenize import inject_positional_add_paths
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.processing.envctx import EnvContext
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.utils.net import ssl_context_for as _ssl_ctx_for
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.core.interfaces.classifier import InputClassifierProtocol

logger = logging.getLogger("ghconcat")

HEADER_DELIM: str = "===== "
DEFAULT_OPENAI_MODEL: str = "o3"
TOK_NONE: str = "none"

_LINE1_RE: re.Pattern[str] = re.compile("^\\s*#\\s*line\\s*1\\d*\\s*$")
_WORKSPACES_SEEN: set[Path] = set()

_LINE_OPS = LineProcessingService(comment_rules=COMMENT_RULES, line1_re=_LINE1_RE, logger=logger)
_INTERPOLATOR = StringInterpolator()
_TEXT_TRANSFORMER = TextTransformer(logger=logger, regex_delim="/")
_ENV_CONTEXT = EnvContext(logger=logger)

_GIT_CLONES: Dict[Tuple[str, str | None], Path] = {}


def _configure_logging(enable_json: bool) -> None:
    """Configure the ghconcat root logger.

    Args:
        enable_json: Whether to enable JSON log formatting.
    """
    prev = getattr(_configure_logging, "_configured_mode", None)
    if prev is not None and prev == bool(enable_json):
        return
    factory = DefaultLoggerFactory(json_logs=enable_json, level=logging.INFO)
    lg = factory.get_logger("ghconcat")
    global logger
    logger = lg
    setattr(_configure_logging, "_configured_mode", bool(enable_json))


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [-x FILE] … [OPTIONS]",
        add_help=False,
        description=(
            "ghconcat – multi-level concatenation, slicing & templating tool\n"
            'Everything after a “-x FILE” is parsed inside the directive-file '
            "context unless another “-x” is encountered."
        ),
    )

    g_loc = p.add_argument_group("Discovery")
    g_rng = p.add_argument_group("Line slicing")
    g_cln = p.add_argument_group("Cleaning")
    g_sub = p.add_argument_group("Substitution")
    g_tpl = p.add_argument_group("Template & output")
    g_ai = p.add_argument_group("AI integration")
    g_misc = p.add_argument_group("Miscellaneous")

    # Discovery
    g_loc.add_argument("-w", "--workdir", metavar="DIR", dest="workdir")
    g_loc.add_argument("-W", "--workspace", metavar="DIR", dest="workspace")
    g_loc.add_argument("-a", "--add-path", metavar="PATH", action="append", dest="add_path")
    g_loc.add_argument("-A", "--exclude-path", metavar="DIR", action="append", dest="exclude_path")
    g_loc.add_argument(
        "--url-depth",
        metavar="N",
        type=int,
        dest="url_depth",
        default=0,
        help="Depth for URL crawling (0 fetch-only, >0 breadth-first scrape).",
    )
    g_loc.add_argument(
        "--url-allow-cross-domain",
        action="store_true",
        dest="url_cross_domain",
        help="Allow cross-domain links during scraping (disabled by default).",
    )
    g_loc.add_argument("-s", "--suffix", metavar="SUF", action="append", dest="suffix")
    g_loc.add_argument("-S", "--exclude-suffix", metavar="SUF", action="append", dest="exclude_suf")

    # Line slicing
    g_rng.add_argument("-n", "--total-lines", metavar="NUM", type=int, dest="total_lines")
    g_rng.add_argument("-N", "--start-line", metavar="LINE", type=int, dest="first_line")
    g_rng.add_argument("-m", "--keep-first-line", dest="first_flags", action="append_const", const="keep")
    g_rng.add_argument("-M", "--no-first-line", dest="first_flags", action="append_const", const="drop")

    # Substitution
    g_sub.add_argument("-y", "--replace", metavar="SPEC", action="append", dest="replace_rules")
    g_sub.add_argument("-Y", "--preserve", metavar="SPEC", action="append", dest="preserve_rules")

    # Cleaning
    g_cln.add_argument("-c", "--remove-comments", action="store_true", dest="rm_comments",
                       help="Enable comment removal.")
    g_cln.add_argument(
        "-C",
        "--no-remove-comments",
        action="store_true",
        dest="no_rm_comments",
        help="Disable comment removal (cancels -c).",
    )
    g_cln.add_argument("-i", "--remove-import", action="store_true", dest="rm_import")
    g_cln.add_argument("-I", "--remove-export", action="store_true", dest="rm_export")
    g_cln.add_argument("-b", "--strip-blank", dest="blank_flags", action="append_const", const="strip")
    g_cln.add_argument("-B", "--keep-blank", dest="blank_flags", action="append_const", const="keep")
    g_cln.add_argument("-K", "--textify-html", action="store_true", dest="strip_html")

    # Template & output
    g_tpl.add_argument("-t", "--template", metavar="FILE", dest="template")
    g_tpl.add_argument("-T", "--child-template", metavar="FILE", dest="child_template")
    g_tpl.add_argument("-o", "--output", metavar="FILE", dest="output")
    g_tpl.add_argument("-O", "--stdout", action="store_true", dest="to_stdout")
    g_tpl.add_argument("-u", "--wrap", metavar="LANG", dest="wrap_lang")
    g_tpl.add_argument("-U", "--no-wrap", action="store_true", dest="unwrap")
    g_tpl.add_argument("-h", "--header", dest="hdr_flags", action="append_const", const="show")
    g_tpl.add_argument("-H", "--no-headers", dest="hdr_flags", action="append_const", const="hide")
    g_tpl.add_argument("-r", "--relative-path", dest="path_flags", action="append_const", const="relative")
    g_tpl.add_argument("-R", "--absolute-path", dest="path_flags", action="append_const", const="absolute")
    g_tpl.add_argument("-l", "--list", action="store_true", dest="list_only")
    g_tpl.add_argument("-L", "--no-list", action="store_true", dest="no_list")
    g_tpl.add_argument("-e", "--env", metavar="VAR=VAL", action="append", dest="env_vars")
    g_tpl.add_argument("-E", "--global-env", metavar="VAR=VAL", action="append", dest="global_env")

    # AI
    g_ai.add_argument("--ai", action="store_true")
    g_ai.add_argument("--ai-model", metavar="MODEL", default=DEFAULT_OPENAI_MODEL, dest="ai_model")
    g_ai.add_argument("--ai-temperature", type=float, metavar="NUM", dest="ai_temperature")
    g_ai.add_argument("--ai-top-p", type=float, metavar="NUM", dest="ai_top_p")
    g_ai.add_argument("--ai-presence-penalty", type=float, metavar="NUM", dest="ai_presence_penalty")
    g_ai.add_argument("--ai-frequency-penalty", type=float, metavar="NUM", dest="ai_frequency_penalty")
    g_ai.add_argument("--ai-system-prompt", metavar="FILE", dest="ai_system_prompt")
    g_ai.add_argument("--ai-seeds", metavar="FILE", dest="ai_seeds")
    g_ai.add_argument("--ai-max-tokens", type=int, metavar="NUM", dest="ai_max_tokens")
    g_ai.add_argument(
        "--ai-reasoning-effort",
        metavar="LEVEL",
        dest="ai_reasoning_effort",
        choices=("low", "medium", "high"),
    )

    # Misc
    g_misc.add_argument("--preserve-cache", action="store_true")
    g_misc.add_argument("--upgrade", action="store_true")
    g_misc.add_argument("--json-logs", action="store_true", dest="json_logs")
    g_misc.add_argument("--help", action="help")

    # NEW: classifier injection (backwards-compatible defaults)
    g_misc.add_argument(
        "--classifier",
        metavar="REF",
        dest="classifier_ref",
        help='Custom classifier as "module.path:ClassName" or "none". '
             "If omitted, the default classifier is used. "
             "You may also set GHCONCAT_CLASSIFIER env var.",
    )
    g_misc.add_argument(
        "--classifier-policies",
        metavar="NAME",
        dest="classifier_policies",
        choices=("standard", "none"),
        default="standard",
        help='Policy preset to register on the classifier (default: "standard").',
    )

    return p


def _fatal(msg: str, code: int = 1) -> None:
    """Log an error and terminate the process."""
    logger.error(msg)
    sys.exit(code)


def _apply_replacements(
        text: str,
        replace_specs: Sequence[str] | None,
        preserve_specs: Sequence[str] | None,
) -> str:
    """Apply replacement/preserve specs to a string."""
    return _TEXT_TRANSFORMER.apply_replacements(text, replace_specs, preserve_specs)


def _expand_tokens(tokens: List[str], inherited_env: Dict[str, str]) -> List[str]:
    """Expand environment variables in tokens."""
    return _ENV_CONTEXT.expand_tokens(tokens, inherited_env, value_flags=_VALUE_FLAGS, none_value=TOK_NONE)


def _post_parse(ns: argparse.Namespace) -> None:
    """Normalize and derive flags after parsing."""
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
    """Call OpenAI and persist the output to a file path."""
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return
    if not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return
    try:
        from ghconcat.ai.ai_client import OpenAIClient
    except Exception as exc:
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")
        return

    client = OpenAIClient(logger=logger)
    try:
        out_path.write_text(
            client.generate_chat_completion(
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
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


def _merge_ns(parent: argparse.Namespace, child: argparse.Namespace) -> argparse.Namespace:
    """Merge a child namespace into a parent namespace with inheritance rules."""
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
    """Parse VAR=VAL items list into a mapping."""
    return _ENV_CONTEXT.parse_items(items, on_error=lambda m: _fatal(m))


def _load_object_from_ref(ref: str) -> Any:
    """Load an object from a 'module.path:ClassName' reference.

    Args:
        ref: A string reference in the form 'module.path:ClassName'.

    Returns:
        The referenced object.

    Raises:
        ImportError: If the module or attribute cannot be loaded.
        AttributeError: If the attribute does not exist in the module.
    """
    module_name, sep, obj_name = (ref or "").partition(":")
    if not module_name or not sep or not obj_name:
        raise ImportError(f"Invalid reference '{ref}'. Expected 'module.path:ClassName'.")
    module = __import__(module_name, fromlist=[obj_name])
    return getattr(module, obj_name)


def _make_classifier(ns: argparse.Namespace) -> InputClassifierProtocol:
    """Construct an InputClassifierProtocol from CLI/env and register policies.

    The function is conservative and fully backwards compatible: if no
    classifier is specified, a DefaultInputClassifier is returned.

    Supported sources:
      * CLI flag: --classifier "module.path:ClassName" or "none"
      * Env var: GHCONCAT_CLASSIFIER (same format)

    Policy preset:
      * --classifier-policies {standard, none}  (default: standard)
    """
    ref = getattr(ns, "classifier_ref", None) or os.getenv("GHCONCAT_CLASSIFIER") or ""
    ref = (ref or "").strip()

    # Build base classifier
    if ref and ref.lower() != "none":
        try:
            cls = _load_object_from_ref(ref)
            classifier: InputClassifierProtocol = cls()  # type: ignore[call-arg]
        except Exception as exc:
            logger.warning(
                "⚠  failed to load classifier %r: %s  → falling back to DefaultInputClassifier",
                ref,
                exc,
            )
            classifier = DefaultInputClassifier()
    else:
        classifier = DefaultInputClassifier()

    # Register default policy preset, if any
    preset = (getattr(ns, "classifier_policies", "standard") or "standard").lower()
    if preset == "standard":
        try:
            from ghconcat.runtime.policies import DefaultPolicies

            DefaultPolicies.register_standard(classifier)
        except Exception as exc:
            logger.warning("⚠  failed to register default policies: %s", exc)

    return classifier


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
    """Execute a directive node with the current configuration."""
    _call_fn = _call_openai if "ghconcat" not in sys.modules else getattr(sys.modules["ghconcat"], "_call_openai")

    # Build the container config (now with optional classifier injection)
    cfg = EngineConfig(
        logger=logger,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
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
        # NEW: let EngineBuilder/ExecutionEngine receive a classifier
        classifier=None,  # resolved per-run (see below)
    )

    builder = EngineBuilder.from_config(cfg)

    # Build the execution engine with a classifier instance
    engine = builder.build(call_openai=_call_fn)
    # Inject a classifier (resolved from root or current namespace *once* per execution)
    # We re-parse the current node just to obtain CLI flags that may define classifier/policies.
    # This preserves full backward compatibility for runs that don't use the new flags.
    tokens_preview = node.tokens or []
    ns_preview = _build_parser().parse_args(tokens_preview or [])
    _post_parse(ns_preview)
    engine._classifier = _make_classifier(ns_preview)  # noqa: SLF001 (intentional, scoped injection)

    return engine.execute_node(
        node,
        ns_parent,
        level=level,
        parent_root=parent_root,
        parent_workspace=parent_workspace,
        inherited_vars=inherited_vars,
        gh_dump=gh_dump,
    )


def _perform_upgrade() -> None:
    """Upgrade the local ghconcat binary."""
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
    except Exception as exc:
        _fatal(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


def _purge_caches() -> None:
    """Purge caches in all workspaces seen during the run."""
    from ghconcat.io.cache_manager import CacheManager

    mgr = CacheManager(logger=logger)
    mgr.purge_all(_WORKSPACES_SEEN)


class GhConcat:
    """Main entry point wrapper for programmatic and CLI execution."""

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """Execute ghconcat with provided arguments.

        Args:
            argv: Raw CLI arguments (excluding program name).

        Returns:
            The combined output dump.
        """
        json_logs = "--json-logs" in argv or os.getenv("GHCONCAT_JSON_LOGS") == "1"
        _configure_logging(json_logs)

        global _SEEN_FILES
        _SEEN_FILES = set()
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
        dparser = DirectiveParser(logger=logger)

        for directive_path, extra_cli in units:
            _SEEN_FILES.clear()
            if directive_path:
                root = dparser.parse(directive_path)
                root.tokens.extend(extra_cli)
            else:
                root = DirNode()
                root.tokens.extend(extra_cli)

            if "--upgrade" in root.tokens:
                (
                    _perform_upgrade
                    if "ghconcat" not in sys.modules
                    else getattr(sys.modules["ghconcat"], "_perform_upgrade")
                )()

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if "--preserve-cache" not in argv:
            _purge_caches()

        return "".join(outputs)


def main() -> NoReturn:
    """CLI entry point with robust error handling."""
    try:
        GhConcat.run(sys.argv[1:])
        raise SystemExit(0)
    except KeyboardInterrupt:
        logger.error("Interrupted by user.")
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:
        if os.getenv("DEBUG") == "1":
            raise
        logger.error("Unexpected error: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
