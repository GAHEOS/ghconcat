from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Sequence, Tuple

from ghconcat.constants import HEADER_DELIM
from ghconcat.logging.factory import DefaultLoggerFactory
from ghconcat.parsing.parser import _build_parser
from ghconcat.parsing.directives import DirNode, DirectiveParser
from ghconcat.parsing.tokenizer import DirectiveTokenizer
from ghconcat.runtime.sdk import _call_openai, _perform_upgrade
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.plugins.registry import get_classifier
from ghconcat.runtime.policies import apply_policies  # ← unified policies
from ghconcat.logging.helpers import get_logger
from ghconcat.runtime.wiring import build_engine_config, build_engine
from ghconcat.runtime.helpers import NamespaceMerger
from ghconcat.utils.imports import load_object_from_ref  # ← unified dynamic import


logger = get_logger('ghconcat')

_SEEN_FILES: set[Path] = set()
_WORKSPACES_SEEN: set[Path] = set()
_GIT_CLONES: Dict[Tuple[str, str | None], Path] = {}


def _configure_logging(enable_json: bool) -> None:
    """Configure process-wide logging once, either JSON or plain text."""
    prev = getattr(_configure_logging, '_configured_mode', None)
    if prev is not None and prev == bool(enable_json):
        return
    factory = DefaultLoggerFactory(json_logs=enable_json, level=logging.INFO)
    lg = factory.get_logger('ghconcat')
    global logger
    logger = lg
    setattr(_configure_logging, '_configured_mode', bool(enable_json))


def _fatal(msg: str, code: int = 1) -> None:
    """Exit the process with a logged error."""
    logger.error(msg)
    sys.exit(code)


def _make_classifier(ns: argparse.Namespace) -> InputClassifierProtocol:
    """Build the input classifier according to CLI flags and plugins.

    Resolution order:
        1) --classifier / GHCONCAT_CLASSIFIER
           - 'plugin:<name>' uses registry factories
           - 'module.path:ClassName' uses dynamic import
           - 'none' → default classifier
        2) Policies via runtime.policies.apply_policies (preset default 'standard')
    """
    ref = getattr(ns, 'classifier_ref', None) or os.getenv('GHCONCAT_CLASSIFIER') or ''
    ref = (ref or '').strip()
    if ref and ref.lower() != 'none':
        if ref.startswith('plugin:'):
            name = ref.split(':', 1)[1].strip()
            factory = get_classifier(name)
            if factory is None:
                logger.warning('⚠  unknown classifier plugin %r – falling back to DefaultInputClassifier', name)
                classifier: InputClassifierProtocol = DefaultInputClassifier()
            else:
                classifier = factory()
        else:
            try:
                cls = load_object_from_ref(ref)  # ← unified loader
                classifier = cls()
            except Exception as exc:
                logger.warning('⚠  failed to load classifier %r: %s  → falling back to DefaultInputClassifier', ref, exc)
                classifier = DefaultInputClassifier()
    else:
        classifier = DefaultInputClassifier()

    preset = (getattr(ns, 'classifier_policies', 'standard') or 'standard').lower()
    if preset != 'none':
        try:
            classifier = apply_policies(classifier, preset)  # ← single point
        except Exception as exc:
            logger.warning('⚠  failed to apply policy set %r: %s; continuing without policies', preset, exc)
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
    """Execute a directive node and return (vars, rendered_output)."""
    # Allow test-time monkeypatch via 'ghconcat' top-level module.
    _call_fn = _call_openai if 'ghconcat' not in sys.modules else getattr(sys.modules['ghconcat'], '_call_openai')

    # Optional custom URL policy loader.
    url_policy_ref = getattr(ns_parent or node, 'url_policy_ref', None)
    policy_loader = None
    if isinstance(url_policy_ref, str) and url_policy_ref and (url_policy_ref.lower() != 'none'):
        try:
            policy_cls = load_object_from_ref(url_policy_ref)  # ← unified loader
            policy_loader = policy_cls
        except Exception as exc:
            logger.warning('⚠  failed to load URL policy %r: %s, continuing with default policy', url_policy_ref, exc)

    cfg = build_engine_config(
        logger=logger,
        header_delim=HEADER_DELIM,
        seen_files=_SEEN_FILES,
        clones_cache=_GIT_CLONES,
        workspaces_seen=_WORKSPACES_SEEN,
        fatal_handler=lambda msg: _fatal(msg),
    )
    engine = build_engine(cfg, call_openai=_call_fn, url_policy_cls=policy_loader)

    tokens_preview = node.tokens or []
    ns_preview = _build_parser().parse_args(tokens_preview or [])
    NamespaceMerger.post_parse(ns_preview)
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
    """Delete workspace caches unless --preserve-cache is set."""
    from ghconcat.io.cache_manager import CacheManager

    mgr = CacheManager(logger=logger)
    mgr.purge_all(_WORKSPACES_SEEN)


class GhConcat:
    """Top-level façade for command-style execution."""

    @staticmethod
    def run(argv: Sequence[str]) -> str:
        """Run the tool with given argv-like sequence and return final text."""
        json_logs = '--json-logs' in argv or os.getenv('GHCONCAT_JSON_LOGS') == '1'
        _configure_logging(json_logs)

        global _SEEN_FILES
        _SEEN_FILES = set()
        _GIT_CLONES.clear()

        units: List[Tuple[Optional[Path], List[str]]] = []
        cli_remainder: List[str] = []

        # Split argv by '-x FILE' directive chunks, preserving trailing flags.
        it = iter(argv)
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

            if '--upgrade' in root.tokens:
                (_perform_upgrade if 'ghconcat' not in sys.modules else getattr(sys.modules['ghconcat'], '_perform_upgrade'))()

            # Pass url policy ref downstream as an attribute on the node.
            url_policy_ref = None
            if '--url-policy' in root.tokens:
                try:
                    idx = root.tokens.index('--url-policy')
                    url_policy_ref = root.tokens[idx + 1]
                except Exception:
                    url_policy_ref = None
            setattr(root, 'url_policy_ref', url_policy_ref)

            _, dump = _execute_node(root, None)
            outputs.append(dump)

        if '--preserve-cache' not in argv:
            _purge_caches()

        return ''.join(outputs)


def main() -> NoReturn:
    """Entry point for `python -m ghconcat`."""
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