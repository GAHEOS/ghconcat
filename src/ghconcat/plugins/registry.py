from __future__ import annotations

"""Minimal plugin registry for classifiers and policy sets with lazy bootstrap.

This registry provides:
- `register_classifier(name, factory)`
- `get_classifier(name)`
- `register_policy_set(name, registrar)`
- `apply_policy_set(name, classifier)`
- `has_policy_set(name)`

It is resilient to import-order issues by lazily bootstrapping the default
'standard' policy set from `ghconcat.runtime.policies` if missing.
"""

from typing import Callable, Dict, Optional
from ghconcat.core.interfaces.classifier import InputClassifierProtocol

# In-memory registries (process-wide)
_CLASSIFIER_FACTORIES: Dict[str, Callable[[], InputClassifierProtocol]] = {}
_POLICY_SETS: Dict[str, Callable[[InputClassifierProtocol], InputClassifierProtocol]] = {}


def register_classifier(name: str, factory: Callable[[], InputClassifierProtocol]) -> None:
    """Register a classifier factory under the given name."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("classifier name must be non-empty")
    _CLASSIFIER_FACTORIES[key] = factory


def get_classifier(name: str) -> Optional[Callable[[], InputClassifierProtocol]]:
    """Return a classifier factory for the given name, if registered."""
    key = (name or "").strip().lower()
    return _CLASSIFIER_FACTORIES.get(key)


def register_policy_set(
    name: str,
    registrar: Callable[[InputClassifierProtocol], Optional[InputClassifierProtocol]],
) -> None:
    """Register a policy-set registrar function.

    The registrar may mutate and/or return the classifier. If it returns None,
    the original classifier is used.
    """
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("policy set name must be non-empty")

    def _wrapper(cls: InputClassifierProtocol) -> InputClassifierProtocol:
        result = registrar(cls)
        return result if result is not None else cls

    _POLICY_SETS[key] = _wrapper


def has_policy_set(name: str) -> bool:
    """Return whether a policy set with the given name is registered."""
    key = (name or "").strip().lower()
    return key in _POLICY_SETS


def _bootstrap_defaults() -> None:
    """Ensure default policy sets are registered (lazy bootstrap).

    This tries to import `ghconcat.runtime.policies`, which is expected to
    call `register_policy_set('standard', ...)` during import. If, for any
    reason, that side effect did not occur, we explicitly register the
    default here to guarantee availability.
    """
    if "standard" in _POLICY_SETS:
        return
    try:
        # Import triggers module-level registration via register_policy_set(...)
        from ghconcat.runtime.policies import DefaultPolicies  # type: ignore

        # Defensive: if the module did not register, register explicitly here.
        if "standard" not in _POLICY_SETS:
            register_policy_set("standard", DefaultPolicies.register_standard)
    except Exception:
        # If defaults cannot be imported, we silently continue:
        # apply_policy_set(...) will still raise a KeyError for unknown names.
        pass


# Perform a best-effort bootstrap at import time to cover common cases,
# while keeping a second guard inside `apply_policy_set` for robustness.
_bootstrap_defaults()


def apply_policy_set(name: str, classifier: InputClassifierProtocol) -> InputClassifierProtocol:
    """Apply a previously registered policy set to the given classifier.

    This function performs a lazy bootstrap if the requested policy set is
    missing, preventing import-order issues in callers.
    """
    key = (name or "").strip().lower()
    fn = _POLICY_SETS.get(key)
    if fn is None:
        # Late bootstrap (covers scenarios where callers import this module
        # before the default policies module is imported).
        _bootstrap_defaults()
        fn = _POLICY_SETS.get(key)
        if fn is None:
            raise KeyError(f"policy set not registered: {name!r}")
    return fn(classifier)