from __future__ import annotations

"""
Minimal plugin registry for classifiers and policy sets with lazy bootstrap.

This registry provides:
- `register_classifier(name, factory)`
- `get_classifier(name)`
- `register_policy_set(name, registrar)`
- `apply_policy_set(name, classifier)`

Implementation notes (unified policies):
- To avoid duplication, `apply_policy_set` delegates to
  `ghconcat.runtime.policies.apply_policies`, after applying a locally
  registered set when available. This keeps backward compatibility with
  external plugins that may still use this module.
"""

from typing import Callable, Dict, Optional

from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.runtime.policies import apply_policies as _apply_policies_rt

_CLASSIFIER_FACTORIES: Dict[str, Callable[[], InputClassifierProtocol]] = {}
_POLICY_SETS: Dict[str, Callable[[InputClassifierProtocol], InputClassifierProtocol]] = {}


def register_classifier(name: str, factory: Callable[[], InputClassifierProtocol]) -> None:
    key = (name or '').strip().lower()
    if not key:
        raise ValueError('classifier name must be non-empty')
    _CLASSIFIER_FACTORIES[key] = factory


def get_classifier(name: str) -> Optional[Callable[[], InputClassifierProtocol]]:
    key = (name or '').strip().lower()
    return _CLASSIFIER_FACTORIES.get(key)


def register_policy_set(name: str, registrar: Callable[[InputClassifierProtocol], Optional[InputClassifierProtocol]]) -> None:
    key = (name or '').strip().lower()
    if not key:
        raise ValueError('policy set name must be non-empty')

    def _wrapper(cls: InputClassifierProtocol) -> InputClassifierProtocol:
        result = registrar(cls)
        return result if result is not None else cls

    _POLICY_SETS[key] = _wrapper


def has_policy_set(name: str) -> bool:
    key = (name or '').strip().lower()
    return key in _POLICY_SETS


def apply_policy_set(name: str, classifier: InputClassifierProtocol) -> InputClassifierProtocol:
    """Backward-compatible API that now delegates to runtime.policies.

    1) If a set is registered locally, apply it first.
    2) Always delegate to runtime `apply_policies` for preset + plugins.
    """
    key = (name or '').strip().lower()
    fn = _POLICY_SETS.get(key)
    if fn is not None:
        classifier = fn(classifier)
    # Delegate to runtime (applies preset 'standard' behavior, entrypoints, env).
    return _apply_policies_rt(classifier, key)