from __future__ import annotations

"""Policy registration and plugin loading for input classification.

This extends the existing DefaultPolicies with a small plugin system:

- `apply_policies(classifier, preset)` applies the built-in preset
  (e.g., "standard") and then loads optional plugins:
    * entry-points group: 'ghconcat.policies' → each entry provides a
      callable like `def register(classifier) -> None: ...`
    * env var GHCONCAT_POLICY_PLUGINS: comma-separated 'module:callable'
      references that will be imported and called in order.

The default behavior (preset='standard') remains identical to earlier
versions, keeping full backwards compatibility for tests and callers.
"""

import logging
import os
from importlib import import_module
from typing import Callable

from ghconcat.core.interfaces.classifier import InputClassifierProtocol

logger = logging.getLogger("ghconcat.policies")


class DefaultPolicies:
    @staticmethod
    def register_standard(classifier: InputClassifierProtocol) -> InputClassifierProtocol:
        """Register the default URL/Git classification policies."""
        def _is_git_scheme(token: str) -> bool:
            t = (token or "").strip().lower()
            return t.startswith("ssh://") or t.startswith("git://")

        classifier.register_policy(
            matcher=_is_git_scheme, include_key="git_path", exclude_key="git_exclude"
        )
        return classifier


# ------------------------------ Plugin utilities ------------------------------

def _call_safely(fn: Callable[[InputClassifierProtocol], None],
                 classifier: InputClassifierProtocol,
                 origin: str) -> None:
    try:
        fn(classifier)
        logger.info("✔ policy plugin applied: %s", origin)
    except Exception as exc:
        logger.warning("⚠  policy plugin failed (%s): %s", origin, exc)


def _load_env_plugins(classifier: InputClassifierProtocol) -> None:
    spec = (os.getenv("GHCONCAT_POLICY_PLUGINS") or "").strip()
    if not spec:
        return
    for ref in (s.strip() for s in spec.split(",") if s.strip()):
        mod_name, sep, obj_name = ref.partition(":")
        if not mod_name or not sep or not obj_name:
            logger.warning("⚠  invalid GHCONCAT_POLICY_PLUGINS entry: %r", ref)
            continue
        try:
            mod = import_module(mod_name)
            fn = getattr(mod, obj_name)
        except Exception as exc:
            logger.warning("⚠  could not import policy plugin %r: %s", ref, exc)
            continue
        _call_safely(fn, classifier, origin=f"env:{ref}")


def _load_entrypoint_plugins(classifier: InputClassifierProtocol) -> None:
    try:
        from importlib.metadata import entry_points
    except Exception:
        return
    try:
        eps = entry_points(group="ghconcat.policies")  # type: ignore[call-arg]
    except Exception:
        return
    for ep in eps:
        try:
            fn = ep.load()
        except Exception as exc:
            logger.warning("⚠  could not load entry-point %s: %s", ep.name, exc)
            continue
        _call_safely(fn, classifier, origin=f"entrypoint:{ep.name}")


def apply_policies(classifier: InputClassifierProtocol, preset: str) -> InputClassifierProtocol:
    """Apply built-in preset and then optional plugins.

    Args:
        classifier: The classifier instance to configure.
        preset: One of {"standard","none"}; others are treated as "none".

    Returns:
        The same classifier for chaining.
    """
    if (preset or "standard").lower() == "standard":
        DefaultPolicies.register_standard(classifier)
    # Optional plugin hooks (no-ops if not provided/installed).
    _load_entrypoint_plugins(classifier)
    _load_env_plugins(classifier)
    return classifier