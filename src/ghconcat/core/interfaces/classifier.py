from __future__ import annotations
import argparse
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class InputClassifierProtocol(Protocol):
    """Protocol for token reclassification between discovery channels.

    Implementations are responsible for moving raw CLI-like tokens to:
      * add_path / exclude_path
      * urls / url_scrape
      * git_path / git_exclude
    and optionally applying pluggable policies.
    """

    def reclassify(self, ns: argparse.Namespace) -> None:
        """Rewrite fields in the argparse namespace in-place."""
        ...

    def register_policy(self, matcher: Callable[[str], bool], include_key: str, exclude_key: str) -> None:
        """Register an external policy that maps tokens based on a matcher."""
        ...
