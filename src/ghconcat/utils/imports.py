from __future__ import annotations

"""
Utilities for dynamic imports.

This module centralizes the logic to load objects from string references
formatted as "module.path:AttrName". It removes duplication across the CLI
and policy loaders and provides consistent error messages.

Public API:
    - load_object_from_ref(ref): object
"""

import importlib
from typing import Any


def load_object_from_ref(ref: str) -> Any:
    """Load an attribute from a module given a 'module:attr' reference.

    Args:
        ref: Reference in the form 'module.path:AttrName'.

    Returns:
        The attribute resolved from the given module.

    Raises:
        ImportError: If the reference is malformed or cannot be resolved.
    """
    module_name, sep, obj_name = (ref or '').partition(':')
    if not module_name or not sep or (not obj_name):
        raise ImportError(f"Invalid reference '{ref}'. Expected 'module.path:AttrName'.")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ImportError(f"Failed to import module '{module_name}': {exc}") from exc
    try:
        return getattr(module, obj_name)
    except Exception as exc:
        raise ImportError(f"Module '{module_name}' has no attribute '{obj_name}': {exc}") from exc