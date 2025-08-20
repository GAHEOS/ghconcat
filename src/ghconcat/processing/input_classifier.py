from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.utils.paths import looks_like_git_spec, looks_like_url


@dataclass
class DefaultInputClassifier(InputClassifierProtocol):
    """Default, test-compatible input classifier.

    This classifier reproduces the behavior of the previous internal function
    `_reclassify_add_exclude` and adds a simple extensibility point via
    `register_policy`.

    Rules:
      - add_path: local paths
      - git_path: git specs (git@..., *.git, known VCS hosts)
      - urls: direct fetch when url_depth == 0
      - url_scrape: scraping seeds when url_depth > 0
      - Exclusions for URLs are applied by removing matching seeds from 'urls'
        and 'url_scrape' (no dedicated exclude lists are stored for URLs).
      - Exclusions for local and git go to: exclude_path and git_exclude.

    The order of evaluation preserves user ordering while deduplicating results.
    """

    _extra_policies: List[Tuple[Callable[[str], bool], str, str]] = field(default_factory=list)

    def register_policy(
        self,
        matcher: Callable[[str], bool],
        include_key: str,
        exclude_key: str,
    ) -> None:
        self._extra_policies.append((matcher, include_key, exclude_key))

    @staticmethod
    def _dedup(seq: List[str]) -> List[str]:
        # Keeps first occurrence order
        return list(dict.fromkeys(seq).keys())

    def _classify_include_key(self, token: str, depth: int) -> str:
        # Extra policies first
        for matcher, include_key, _ex_key in self._extra_policies:
            if matcher(token):
                return include_key

        if looks_like_git_spec(token):
            return "git_path"
        if looks_like_url(token):
            return "url_scrape" if depth > 0 else "urls"
        return "add_path"

    def _classify_exclude_sink(self, token: str) -> str | None:
        # Extra policies first
        for matcher, _in_key, ex_key in self._extra_policies:
            if matcher(token):
                return ex_key

        if looks_like_git_spec(token):
            return "git_exclude"
        if looks_like_url(token):
            # URLs are "excluded" by removing from urls/url_scrape; return None
            return None
        return "exclude_path"

    def reclassify(self, ns: argparse.Namespace) -> None:
        depth = int(getattr(ns, "url_depth", 0) or 0)

        add_local = list(getattr(ns, "add_path", []) or [])
        exc_local = list(getattr(ns, "exclude_path", []) or [])

        new_add_local: List[str] = []
        new_exc_local: List[str] = []
        new_urls: List[str] = []
        new_url_scrape: List[str] = []
        new_git_inc: List[str] = []
        new_git_exc: List[str] = []

        # Include side
        for tok in add_local:
            key = self._classify_include_key(tok, depth)
            if key == "git_path":
                new_git_inc.append(tok)
            elif key == "urls":
                new_urls.append(tok)
            elif key == "url_scrape":
                new_url_scrape.append(tok)
            else:
                new_add_local.append(tok)

        # Exclude side
        for tok in exc_local:
            sink = self._classify_exclude_sink(tok)
            if sink == "git_exclude":
                new_git_exc.append(tok)
            elif sink == "exclude_path":
                new_exc_local.append(tok)
            else:
                # URL exclusion: remove from both include lists
                new_urls = [u for u in new_urls if u != tok]
                new_url_scrape = [u for u in new_url_scrape if u != tok]

        # Dedup and write back
        ns.add_path = self._dedup(new_add_local)
        ns.exclude_path = self._dedup(new_exc_local)
        ns.urls = self._dedup(new_urls)
        ns.url_scrape = self._dedup(new_url_scrape)
        ns.git_path = self._dedup(new_git_inc)
        ns.git_exclude = self._dedup(new_git_exc)