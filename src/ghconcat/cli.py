from __future__ import annotations

"""CLI wiring. Now consumes decoupled helper classes and constants."""

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Sequence, Tuple

from ghconcat.constants import HEADER_DELIM
from ghconcat.logging.factory import DefaultLoggerFactory
from ghconcat.parsing.parser import _build_parser
from ghconcat.parsing.directives import DirNode, DirectiveParser
from ghconcat.parsing.tokenizer import DirectiveTokenizer
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.processing.envctx import EnvContext
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.runtime.sdk import _call_openai, _perform_upgrade
from ghconcat.utils.net import ssl_context_for as _ssl_ctx_for
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.runtime.helpers import TextReplacer, EnvExpander, NamespaceMerger

logger = logging.getLogger('ghconcat')

TOK_NONE: str = 'none'
_LINE1_RE: re.Pattern[str] = re.compile(r'^\s*#\s*line\s*1\d*\s*$')
_SEEN_FILES: set[Path] = set()
_WORKSPACES_SEEN: set[Path] = set()
_GIT_CLONES: Dict[Tuple[str, str | None], Path] = {}

_LINE_OPS = LineProcessingService(comment_rules=COMMENT_RULES, line1_re=_LINE1_RE, logger=logger)
_INTERPOLATOR = StringInterpolator()
_TEXT_TRANSFORMER = TextTransformer(logger=logger, regex_delim='/')
_ENV_CONTEXT = EnvContext(logger=logger)


def _configure_logging(enable_json: bool) -> None:
    prev = getattr(_configure_logging, '_configured_mode', None)
    if prev is not None and prev == bool(enable_json):
        return
    factory = DefaultLoggerFactory(json_logs=enable_json, level=logging.INFO)
    lg = factory.get_logger('ghconcat')
    global logger
    logger = lg
    setattr(_configure_logging, '_configured_mode', bool(enable_json))


def _fatal(msg: str, code: int = 1) -> None:
    logger.error(msg)
    sys.exit(code)


def _load_object_from_ref(ref: str) -> Any:
    """Import 'module:ClassOrFunc' and return the attribute."""
    module_name, sep, obj_name = (ref or '').partition(':')
    if not module_name or not sep or (not obj_name):
        raise ImportError(f"Invalid reference '{ref}'. Expected 'module.path:ClassName'.")
    module = __import__(module_name, fromlist=[obj_name])
    return getattr(module, obj_name)


def _make_classifier(ns: argparse.Namespace) -> InputClassifierProtocol:
    ref = getattr(ns, 'classifier_ref', None) or os.getenv('GHCONCAT_CLASSIFIER') or ''
    ref = (ref or '').strip()
    if ref and ref.lower() != 'none':
        try:
            cls = _load_object_from_ref(ref)
            classifier: InputClassifierProtocol = cls()
        except Exception as exc:
            logger.warning('⚠  failed to load classifier %r: %s  → falling back to DefaultInputClassifier', ref, exc)
            classifier = DefaultInputClassifier()
    else:
        classifier = DefaultInputClassifier()
    preset = (getattr(ns, 'classifier_policies', 'standard') or 'standard').lower()
    if preset == 'standard':
        try:
            from ghconcat.runtime.policies import DefaultPolicies
            DefaultPolicies.register_standard(classifier)
        except Exception as exc:
            logger.warning('⚠  failed to register default policies: %s', exc)
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
    _call_fn = _call_openai if 'ghconcat' not in sys.modules else getattr(sys.modules['ghconcat'], '_call_openai')

    replacer = TextReplacer(logger=logger)
    envx = EnvExpander(logger=logger)
    merger = NamespaceMerger(logger=logger)

    # Allow a URL policy override from CLI (stored in ns after parsing).
    url_policy_ref = getattr(ns_parent or node, 'url_policy_ref', None)  # type: ignore[attr-defined]
    policy_loader = None
    if isinstance(url_policy_ref, str) and url_policy_ref and url_policy_ref.lower() != 'none':
        try:
            policy_cls = _load_object_from_ref(url_policy_ref)
            policy_loader = policy_cls  # we pass the class into DefaultUrlFetcherFactory builder later
        except Exception as exc:
            logger.warning('⚠  failed to load URL policy %r: %s, continuing with default policy', url_policy_ref, exc)

    cfg = EngineConfig(
        logger=logger,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
        clones_cache=_GIT_CLONES,
        workspaces_seen=_WORKSPACES_SEEN,
        ssl_ctx_provider=_ssl_ctx_for,
        parser_factory=_build_parser,
        post_parse=merger.post_parse,
        merge_ns=merger.merge,
        expand_tokens=envx.expand_tokens,
        parse_env_items=envx.parse_items,
        interpolate=_INTERPOLATOR.interpolate,
        apply_replacements=replacer.apply,
        slice_lines=_LINE_OPS.slice_lines,
        clean_lines=_LINE_OPS.clean_lines,
        fatal=lambda msg: _fatal(msg),
        classifier=None,
    )
    builder = EngineBuilder.from_config(cfg)

    # When a policy loader is present, we overwrite the default UrlFetcherFactory
    # through EngineBuilder injection by late-binding in build().
    if policy_loader is not None:
        setattr(builder, '_url_policy_loader', policy_loader)  # ad-hoc field used in build()

    engine = builder.build(call_openai=_call_fn)

    tokens_preview = node.tokens or []
    ns_preview = _build_parser().parse_args(tokens_preview or [])
    merger.post_parse(ns_preview)
    engine._classifier = _make_classifier(ns_preview)
    return engine.execute_node(
        node,
        ns_parent,
        level=level,
        parent_root=parent_root,
        parent_workspace=parent_workspace,
        inherited_vars=inherited_vars,
        gh_dump=gh_dump,
    )


def _purge_caches() -> None:
    from ghconcat.io.cache_manager import CacheManager
    mgr = CacheManager(logger=logger)
    mgr.purge_all(_WORKSPACES_SEEN)


class GhConcat:
    @staticmethod
    def run(argv: Sequence[str]) -> str:
        json_logs = '--json-logs' in argv or os.getenv('GHCONCAT_JSON_LOGS') == '1'
        _configure_logging(json_logs)

        global _SEEN_FILES
        _SEEN_FILES = set()
        _GIT_CLONES.clear()

        units: List[Tuple[Optional[Path], List[str]]] = []
        cli_remainder: List[str] = []
        it = iter(argv)

        # Parse '-x FILE' blocks while preserving remainder flags.
        for tok in it:
            if tok in ('-x', '--directives'):
                try:
                    fpath = Path(next(it))
                except StopIteration:
                    _fatal('missing FILE after -x/--directives')
                if not fpath.exists():
                    _fatal(f'directive file {fpath} not found')
                units.append((fpath, DirectiveTokenizer.inject_positional_add_paths(cli_remainder)))
                cli_remainder = []
            else:
                cli_remainder.append(tok)

        if not units:
            units.append((None, DirectiveTokenizer.inject_positional_add_paths(cli_remainder)))
        elif cli_remainder:
            last_path, last_cli = units[-1]
            units[-1] = (last_path, last_cli + DirectiveTokenizer.inject_positional_add_paths(cli_remainder))

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

            # Detect upgrade early.
            if '--upgrade' in root.tokens:
                (_perform_upgrade if 'ghconcat' not in sys.modules else getattr(sys.modules['ghconcat'],
                                                                                '_perform_upgrade'))()

            # Extract --url-policy if present in this unit's tokens; store for _execute_node.
            url_policy_ref = None
            if '--url-policy' in root.tokens:
                try:
                    idx = root.tokens.index('--url-policy')
                    url_policy_ref = root.tokens[idx + 1]
                except Exception:
                    url_policy_ref = None
            setattr(root, 'url_policy_ref', url_policy_ref)  # pass-through for _execute_node

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if '--preserve-cache' not in argv:
            _purge_caches()

        return ''.join(outputs)


def main() -> NoReturn:
    try:
        GhConcat.run(sys.argv[1:])
        raise SystemExit(0)
    except KeyboardInterrupt:
        logger.error('Interrupted by user.')
        raise SystemExit(130)
    except BrokenPipeError:
        raise SystemExit(0)
    except Exception as exc:
        if os.getenv('DEBUG') == '1':
            raise
        logger.error('Unexpected error: %s', exc)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
