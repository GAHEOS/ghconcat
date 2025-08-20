from __future__ import annotations

import argparse
from typing import Callable, Protocol


class InputClassifierProtocol(Protocol):
    """Protocol that encapsulates classification of user-provided inputs
    into discovery buckets (local paths, git specs, direct URLs, scrape seeds).

    Implementations are expected to mutate the argparse.Namespace in place,
    filling the attributes:
      - add_path, exclude_path
      - git_path, git_exclude
      - urls, url_scrape

    The goal is to keep ExecutionEngine agnostic of classification details.
    """

    def reclassify(self, ns: argparse.Namespace) -> None:
        """Inspect and mutate `ns` to normalize add/exclude inputs."""
        ...

    def register_policy(
        self,
        matcher: Callable[[str], bool],
        include_key: str,
        exclude_key: str,
    ) -> None:
        """Optionally register an extra source policy to extend classification.

        Args:
            matcher: Returns True if the token matches a custom source.
            include_key: Target include list name in Namespace (e.g., 'add_path', 'git_path', 'urls', 'url_scrape').
            exclude_key: Target exclude list name in Namespace (e.g., 'exclude_path', 'git_exclude').
        """
        ...