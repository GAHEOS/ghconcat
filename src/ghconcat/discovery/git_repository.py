import logging
import os
import subprocess
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed


class GitRepositoryManager:
    """High-level Git repository handler for ghconcat.

    This class encapsulates parsing, shallow cloning and file collection logic
    used by the CLI flags ``-g/--git-path`` and ``-G/--git-exclude``.

    Design goals
    ------------
    • Preserve legacy behavior 1:1:
        - Cache layout under ``<workspace>/.ghconcat_gitcache``.
        - Shallow clones (``--depth 1``), optional branch (``--single-branch``).
        - Include/exclude suffix semantics identical to the monolith.
        - Skip ``.git`` directories; do not treat ``.ghconcat_gitcache`` as hidden.
        - Ignore ``.pyc`` / ``.pyo``.
    • No dependency on the monolithic module; raise exceptions on failures and
      let the caller decide fatal handling (to avoid circular imports).
    • Optional shared clone cache (in-memory) to match the previous process-
      wide optimization.

    Parameters
    ----------
    workspace:
        Absolute or relative path for the workspace root. The cache directory
        is created as ``workspace/.ghconcat_gitcache``.
    logger:
        Optional logger to keep consistent log format with ghconcat.
    clones_cache:
        Optional mapping used to memoize clone destinations per (url, branch)
        during the process lifetime. When provided, it will be both read and
        updated by the manager, preserving the previous behavior.
    """

    def __init__(
        self,
        workspace: Path,
        *,
        logger: Optional[logging.Logger] = None,
        clones_cache: Optional[Dict[Tuple[str, Optional[str]], Path]] = None,
    ) -> None:
        self._workspace = Path(workspace).resolve()
        self._cache_dir = self._workspace / ".ghconcat_gitcache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = logger or logging.getLogger("ghconcat.git")
        self._clones = clones_cache if clones_cache is not None else {}

    @staticmethod
    def parse_spec(spec: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Parse a ``-g/-G`` SPEC into (repo_url, branch, sub_path).

        Accepted syntax:
            URL[ ^BRANCH ][ /SUBPATH ]

        Behavior matches legacy semantics:
          • For HTTP(S) URLs without an explicit ``^BRANCH``, a trailing path
            beyond ``/owner/repo`` becomes ``SUBPATH``.
          • For ``git@host:owner/repo`` the same rule applies.
          • ``.git`` is appended to HTTP(S) URLs lacking it.

        Examples
        --------
        GitRepositoryManager.parse_spec("git@github.com:GAHEOS/ghconcat")
            -> ("git@github.com:GAHEOS/ghconcat.git", None, None)

        GitRepositoryManager.parse_spec("https://github.com/org/repo^dev/src")
            -> ("https://github.com/org/repo.git", "dev", "src")
        """
        if "^" in spec:
            url_part, tail = spec.split("^", 1)
            if "/" in tail:
                branch, sub_path = tail.split("/", 1)
                sub_path = sub_path.lstrip("/")
            else:
                branch, sub_path = tail, None
        else:
            url_part, branch, sub_path = spec, None, None

        if sub_path is None:
            if url_part.startswith("http"):
                parsed = _urlparse(url_part)
                segs = parsed.path.lstrip("/").split("/")
                if len(segs) > 2:
                    sub_path = "/".join(segs[2:])
                    url_part = parsed._replace(  # type: ignore[attr-defined]
                        path="/" + "/".join(segs[:2])
                    ).geturl()
            elif url_part.startswith("git@"):
                host, path = url_part.split(":", 1)
                segs = path.split("/")
                if len(segs) > 2:
                    sub_path = "/".join(segs[2:])
                    url_part = f"{host}:{'/'.join(segs[:2])}"

        if url_part.startswith("http") and not url_part.endswith(".git"):
            url_part += ".git"

        return url_part, branch, sub_path

    def git_cache_root(self) -> Path:
        """Return the on-disk directory that stores shallow clones."""
        return self._cache_dir

    def clone_repo(self, repo_url: str, branch: Optional[str]) -> Path:
        """Shallow-clone *repo_url* into the cache if needed and return the path.

        Parameters
        ----------
        repo_url:
            Canonical Git URL. HTTP(S) URLs should already end with ``.git``.
        branch:
            Optional branch. When provided, ``--single-branch`` is used.

        Returns
        -------
        Path
            The working tree path inside the workspace cache.

        Raises
        ------
        Exception
            On any failure during clone.
        """
        key = (repo_url, branch)
        cached = self._clones.get(key)
        if cached and cached.exists():
            return cached

        digest = sha1(f"{repo_url}@{branch or 'HEAD'}".encode()).hexdigest()[:12]
        dst = self._cache_dir / digest

        if not dst.exists():
            cmd = ["git", "clone", "--depth", "1"]
            if branch:
                cmd += ["--branch", branch, "--single-branch"]
            cmd += [repo_url, str(dst)]
            try:
                subprocess.check_call(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self._log.info("✔ cloned %s (%s) → %s", repo_url, branch or "default", dst)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"could not clone {repo_url}: {exc}") from exc

        self._clones[key] = dst
        return dst

    def collect_files(
        self,
        git_specs: Sequence[str],
        git_exclude_specs: Sequence[str] | None,
        suffixes: Sequence[str],
        exclude_suf: Sequence[str],
    ) -> List[Path]:
        """Resolve Git specs into a concrete, filtered list of file paths.

        Matching rules (unchanged):
          • Hidden directories are allowed except for ``.git`` itself.
          • Suffix include-list wins over exclude-list.
          • Explicit file exclusions from ``-G`` are applied strictly.
          • Python bytecode (``.pyc``/``.pyo``) is always ignored.

        Parameters
        ----------
        git_specs:
            Sequence of inclusions as given to ``-g``.
        git_exclude_specs:
            Sequence of exclusions as given to ``-G``.
        suffixes:
            Include-list from ``-s`` (with or without leading dots).
        exclude_suf:
            Exclude-list from ``-S`` (with or without leading dots).

        Returns
        -------
        List[Path]
            Sorted list of absolute filesystem paths.
        """
        if not git_specs:
            return []

        include_roots: list[Path] = []
        exclude_roots: list[Path] = []

        # Unified suffix handling (include > exclude)
        inc_set, exc_set = compute_suffix_filters(suffixes, exclude_suf)

        for spec in git_specs:
            repo, branch, sub = self.parse_spec(spec)
            root = self.clone_repo(repo, branch)
            include_roots.append(root / sub if sub else root)

        for spec in git_exclude_specs or []:
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
                    self._log.warning("⚠  %s does not exist – skipped", root)
                    continue
                self._log.debug("↪  %s missing, walking ancestor %s", root, anc)
                root = anc

            if root.is_file():
                if root.resolve() not in excl_files and not _skip_suffix(root):
                    collected.add(root.resolve())
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if (Path(dirpath, d).resolve() not in excl_dirs) and d != ".git"
                ]

                for fn in filenames:
                    fp = Path(dirpath, fn)
                    if fp.suffix in {".pyc", ".pyo"}:
                        continue
                    if fp.resolve() in excl_files:
                        continue
                    if _skip_suffix(fp):
                        continue
                    collected.add(fp.resolve())

        return sorted(collected, key=str)


def _urlparse(url: str):
    import urllib.parse as _u

    return _u.urlparse(url)