from __future__ import annotations

"""'Policy registration and plugin loading for input classification.

This extends the existing DefaultPolicies with a small plugin system:

- `apply_policies(classifier, preset)` applies the built-in preset
  (e.g., "standard") and then loads optional plugins:
    * entry-points group: \'ghconcat.policies\' → each entry provides a
      callable like `def register(classifier) -> None: ...`
    * env var GHCONCAT_POLICY_PLUGINS: comma-separated \'module:callable\'
      references that will be imported and called in order.

The default behavior (preset=\'standard\') remains identical to earlier
versions, keeping full backwards compatibility for tests and callers.
'"""

import logging
import os
from typing import Callable

from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.utils.imports import load_object_from_ref  # ← unified dynamic import

logger = logging.getLogger('ghconcat.policies')


class DefaultPolicies:
    @staticmethod
    def register_standard(classifier: InputClassifierProtocol) -> InputClassifierProtocol:
        def _is_git_scheme(token: str) -> bool:
            t = (token or '').strip().lower()
            return t.startswith('ssh://') or t.startswith('git://')

        classifier.register_policy(matcher=_is_git_scheme, include_key='git_path', exclude_key='git_exclude')
        return classifier


def _call_safely(fn: Callable[[InputClassifierProtocol], None], classifier: InputClassifierProtocol,
                 origin: str) -> None:
    try:
        fn(classifier)
        logger.info('✔ policy plugin applied: %s', origin)
    except Exception as exc:
        logger.warning('⚠  policy plugin failed (%s): %s', origin, exc)


def _load_env_plugins(classifier: InputClassifierProtocol) -> None:
    spec = (os.getenv('GHCONCAT_POLICY_PLUGINS') or '').strip()
    if not spec:
        return
    for ref in (s.strip() for s in spec.split(',') if s.strip()):
        try:
            fn = load_object_from_ref(ref)  # ← replaces ad-hoc import logic
            if not callable(fn):
                logger.warning('⚠  policy plugin %r is not callable; skipped', ref)
                continue
        except Exception as exc:
            logger.warning('⚠  could not import policy plugin %r: %s', ref, exc)
            continue
        _call_safely(fn, classifier, origin=f'env:{ref}')


def _load_entrypoint_plugins(classifier: InputClassifierProtocol) -> None:
    try:
        from importlib.metadata import entry_points
    except Exception:
        return
    try:
        eps = entry_points(group='ghconcat.policies')
    except Exception:
        return
    for ep in eps:
        try:
            fn = ep.load()
        except Exception as exc:
            logger.warning('⚠  could not load entry-point %s: %s', ep.name, exc)
            continue
        _call_safely(fn, classifier, origin=f'entrypoint:{ep.name}')


def apply_policies(classifier: InputClassifierProtocol, preset: str) -> InputClassifierProtocol:
    if (preset or 'standard').lower() == 'standard':
        DefaultPolicies.register_standard(classifier)
    _load_entrypoint_plugins(classifier)
    _load_env_plugins(classifier)
    return classifier
