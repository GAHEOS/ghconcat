from __future__ import annotations

"""Small logging helpers to standardize ghconcat logger names."""

import logging


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the 'ghconcat' namespace.

    Args:
        name: Optional dotted suffix. If it already starts with 'ghconcat',
              it is returned unchanged.

    Returns:
        A configured `logging.Logger` instance.
    """
    if not name or name == "ghconcat":
        return logging.getLogger("ghconcat")
    if name.startswith("ghconcat"):
        return logging.getLogger(name)
    return logging.getLogger(f"ghconcat.{name}")