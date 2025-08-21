from __future__ import annotations
"""Git repository discovery and cached cloning.

This module provides a small manager that:
- Parses flexible repository specifications (URL + optional branch + subpath).
- Clones repositories into a workspace-local cache with deduplication.
- Walks repo trees to collect files filtered by suffix constraints.

Compatibility:
    Behavior is preserved for tests. The previous helper `_urlparse` is removed
    and replaced with `urllib.parse.urlparse` directly inside `parse_spec` to
    reduce code duplication and improve cohesion.
"""

import logging
import os
import subprocess
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse  # ← standard lib, replaces the old _urlparse()

from ghconcat.logging.helpers import get_logger
from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed


class GitRepositoryManager:
    def __init__(
        self,
        workspace: Path,
        *,
        logger: Optional[logging.Logger] = None,
        clones_cache: Optional[Dict[Tuple[str, Optional[str]], Path]] = None,
    ) -> None:
        """Initialize the manager with a workspace-local cache root."""
        self._workspace = Path(workspace).resolve()
        self._cache_dir = self._workspace / '.ghconcat_gitcache'
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger or get_logger('git')
        self._clones = clones_cache if clones_cache is not None else {}

    @staticmethod
    def parse_spec(spec: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse a flexible git spec into (repo_url, branch, sub_path).

        Supported forms:
            - "<URL>.git"
            - "<URL>^branch[/sub/path]"
            - "git@host:org/repo[.git][/sub/path]"
            - "https://host/org/repo[.git][/sub/path]"

        Behavior:
            - If a path component beyond "org/repo" is present, it becomes `sub_path`.
            - If the URL is HTTP(S) and doesn't end with ".git", the suffix is appended.
        """
        if '^' in spec:
            url_part, tail = spec.split('^', 1)
            if '/' in tail:
                branch, sub_path = tail.split('/', 1)
                sub_path = sub_path.lstrip('/')
            else:
                branch, sub_path = (tail, None)
        else:
            url_part, branch, sub_path = (spec, None, None)

        # Derive sub_path for common hosting schemes when not explicitly provided.
        if sub_path is None:
            if url_part.startswith('http'):
                parsed = urlparse(url_part)
                segs = parsed.path.lstrip('/').split('/')
                if len(segs) > 2:
                    sub_path = '/'.join(segs[2:])
                    url_part = parsed._replace(path='/' + '/'.join(segs[:2])).geturl()
            elif url_part.startswith('git@'):
                host, path = url_part.split(':', 1)
                segs = path.split('/')
                if len(segs) > 2:
                    sub_path = '/'.join(segs[2:])
                    url_part = f"{host}:{'/'.join(segs[:2])}"

        if url_part.startswith('http') and (not url_part.endswith('.git')):
            url_part += '.git'

        return (url_part, branch, sub_path)

    def git_cache_root(self) -> Path:
        """Return the cache root."""
        return self._cache_dir

    def clone_repo(self, repo_url: str, branch: Optional[str]) -> Path:
        """Clone (shallow) the repository, reusing cache when possible."""
        key = (repo_url, branch)
        cached = self._clones.get(key)
        if cached and cached.exists():
            return cached

        digest = sha1(f"{repo_url}@{branch or 'HEAD'}".encode()).hexdigest()[:12]
        dst = self._cache_dir / digest
        if not dst.exists():
            cmd = ['git', 'clone', '--depth', '1']
            if branch:
                cmd += ['--branch', branch, '--single-branch']
            cmd += [repo_url, str(dst)]
            try:
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._log.info('✔ cloned %s (%s) → %s', repo_url, branch or 'default', dst)
            except Exception as exc:
                raise RuntimeError(f'could not clone {repo_url}: {exc}') from exc

        self._clones[key] = dst
        return dst

    def collect_files(
        self,
        git_specs: Sequence[str],
        git_exclude_specs: Sequence[str] | None,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
    ) -> List[Path]:
        """Collect files from cloned repositories applying suffix filters and excludes."""
        if not git_specs:
            return []

        include_roots: list[Path] = []
        exclude_roots: list[Path] = []
        inc_set, exc_set = compute_suffix_filters(suffixes, exclude_suf)

        for spec in git_specs:
            repo, branch, sub = self.parse_spec(spec)
            root = self.clone_repo(repo, branch)
            include_roots.append(root / sub if sub else root)

        for spec in (git_exclude_specs or []):
            repo, branch, sub = self.parse_spec(spec)
            root = self.clone_repo(repo, branch)
            exclude_roots.append(root / sub if sub else root)

        excl_files = {p.resolve() for p in exclude_roots if p.is_file()}
        excl_dirs = {p.resolve() for p in exclude_roots if p.is_dir()}

        def _skip_suffix(p: Path) -> bool:
            return not is_suffix_allowed(p.name, inc_set, exc_set)

        collected: set[Path] = set()

        for root in include_roots:
            if not root.exists():
                anc = next((p for p in root.parents if p.exists()), None)
                if anc is None:
                    self._log.warning('⚠  %s does not exist – skipped', root)
                    continue
                self._log.debug('↪  %s missing, walking ancestor %s', root, anc)
                root = anc

            if root.is_file():
                if root.resolve() not in excl_files and (not _skip_suffix(root)):
                    collected.add(root.resolve())
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if Path(dirpath, d).resolve() not in excl_dirs and d != '.git'
                ]
                for fn in filenames:
                    fp = Path(dirpath, fn)
                    if fp.suffix in {'.pyc', '.pyo'}:
                        continue
                    if fp.resolve() in excl_files:
                        continue
                    if _skip_suffix(fp):
                        continue
                    collected.add(fp.resolve())

        return sorted(collected, key=str)