from __future__ import annotations

from typing import Callable
from ghconcat.core.interfaces.classifier import InputClassifierProtocol


class DefaultPolicies:
    """Register common classifier policies.

    The default policies are intentionally conservative to avoid
    shadowing built-in heuristics in ``DefaultInputClassifier``.
    For example, we *do not* add a general HTTP(S) matcher here
    because the default classifier already routes those tokens
    and accounts for ``--url-depth`` to decide between
    ``urls`` and ``url_scrape``.

    Current additions:
      * Treat ``ssh://`` and ``git://`` URIs as Git specs
        (map to ``git_path`` / ``git_exclude``), since the
        default heuristic focuses on HTTP(S) or scp-like forms.
    """

    @staticmethod
    def register_standard(
        classifier: InputClassifierProtocol,
    ) -> InputClassifierProtocol:
        """Register a conservative set of default policies.

        Args:
            classifier: A classifier that supports ``register_policy``.

        Returns:
            The same classifier instance (for chaining).
        """

        def _is_git_scheme(token: str) -> bool:
            t = (token or "").strip().lower()
            return t.startswith("ssh://") or t.startswith("git://")

        # Route ssh:// / git:// to Git buckets.
        classifier.register_policy(
            matcher=_is_git_scheme,
            include_key="git_path",
            exclude_key="git_exclude",
        )

        return classifier