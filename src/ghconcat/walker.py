import argparse
import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple


def _hidden(p: Path) -> bool:
    """Return True if *p* has any hidden segment (leading dot component)."""
    return any(part.startswith(".") for part in p.parts)


def _is_within(path: Path, parent: Path) -> bool:
    """Return True if *path* is contained inside *parent*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class WalkerAppender:
    """
    Filesystem walker and content appender with header, cleaning and replacement
    support. It mirrors ghconcat's established semantics while allowing OOP use.

    The class is dependency-injected to avoid tight coupling with the monolithic
    module and to keep behavior 1:1 with the existing implementation.
    """

    def __init__(
        self,
        *,
        read_file_as_lines,
        html_to_text,  # kept for constructor compatibility (unused here)
        apply_replacements,
        slice_lines,
        clean_lines,
        header_delim: str,
        seen_files: Set[str],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Parameters
        ----------
        read_file_as_lines:
            Callable(Path) -> List[str]. Uniform text reader for any file type.
        html_to_text:
            Callable(str) -> str. (Deprecated here; handled by the registry)
        apply_replacements:
            Callable(str, Sequence[str] | None, Sequence[str] | None) -> str.
        slice_lines:
            Callable(raw_lines, begin, total, keep_header) -> List[str].
        clean_lines:
            Callable(lines, ext, rm_simple=..., rm_all=..., rm_imp=..., rm_exp=..., keep_blank=...) -> List[str].
        header_delim:
            Banner delimiter string, e.g. "===== ".
        seen_files:
            Set of header paths already emitted (dedup across contexts/units).
        logger:
            Optional logger; defaults to module logger.
        """
        self._read_file_as_lines = read_file_as_lines
        self._apply_replacements = apply_replacements
        self._slice = slice_lines
        self._clean = clean_lines
        self._HEADER_DELIM = header_delim
        self._SEEN_FILES = seen_files
        self._log = logger or logging.getLogger("ghconcat.walker")

    def gather_files(
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """
        Walk *add_path* and return every file that matches inclusion/exclusion
        rules. Explicit files always win. Hidden files and .pyc/.pyo are skipped.

        Semantics are intentionally identical to the legacy _gather_files().
        """
        collected: Set[Path] = set()

        explicit_files = [p for p in add_path if p.is_file()]
        dir_paths = [p for p in add_path if not p.is_file()]

        suffixes = [s if s.startswith(".") else f".{s}" for s in suffixes]
        exclude_suf = [s if s.startswith(".") else f".{s}" for s in exclude_suf]
        excl_set = set(exclude_suf) - set(suffixes)

        ex_dirs = {d.resolve() for d in exclude_dirs}

        def _dir_excluded(path: Path) -> bool:
            return any(_is_within(path, ex) for ex in ex_dirs)

        for fp in explicit_files:
            collected.add(fp.resolve())

        for root in dir_paths:
            if not root.exists():
                self._log.error("⚠  %s does not exist – skipped", root)
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not d.startswith(".") and not _dir_excluded(Path(dirpath, d))
                ]
                for fn in filenames:
                    fp = Path(dirpath, fn)
                    if _hidden(fp) or _dir_excluded(fp):
                        continue
                    if suffixes and not any(fp.name.endswith(s) for s in suffixes):
                        continue
                    if any(fp.name.endswith(s) for s in excl_set):
                        continue
                    if fp.name.endswith((".pyc", ".pyo")):
                        continue
                    collected.add(fp.resolve())

        return sorted(collected, key=str)

    def concat_files(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """
        Concatenate *files* applying slicing, cleaning, header emission, optional
        wrapping and the replace/preserve engine. Behavior is identical to the
        legacy _concat_files() function, with the only change that HTML
        textification is now delegated to the ReaderRegistry (via a pluggable
        HtmlToTextReader) instead of being handled here.
        """
        parts: List[str] = []

        for idx, fp in enumerate(files):
            ext = fp.suffix.lower()

            # Read raw lines via the unified registry-aware reader
            raw_lines = self._read_file_as_lines(fp)

            # Keep the legacy PDF special-case for comment cleaning rules
            if fp.suffix.lower() == ".pdf":
                ext = ""

            body_lines = self._clean(
                self._slice(raw_lines, ns.first_line, ns.total_lines, ns.keep_header),
                ext,
                rm_simple=ns.rm_simple or ns.rm_all,
                rm_all=ns.rm_all,
                rm_imp=ns.rm_import,
                rm_exp=ns.rm_export,
                keep_blank=ns.keep_blank,
            )

            if ns.list_only:
                rel = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)
                parts.append(rel + "\n")
                continue

            if not body_lines or not "".join(body_lines).strip():
                continue

            hdr_path = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)

            if not ns.skip_headers and hdr_path not in self._SEEN_FILES:
                parts.append(f"{self._HEADER_DELIM}{hdr_path} {self._HEADER_DELIM}\n")
                self._SEEN_FILES.add(hdr_path)

            body = "".join(body_lines)

            body = self._apply_replacements(
                body,
                getattr(ns, "replace_rules", None),
                getattr(ns, "preserve_rules", None),
            )

            parts.append(body)

            if wrapped is not None:
                wrapped.append((hdr_path, body.rstrip()))

            if ns.keep_blank and (
                idx < len(files) - 1
                or (
                    idx == len(files) - 1
                    and ns.total_lines is None
                    and ns.first_line is None
                )
            ):
                parts.append("\n")

        return "".join(parts)