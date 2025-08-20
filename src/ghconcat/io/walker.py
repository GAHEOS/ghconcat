from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from ghconcat.core.interfaces import WalkerProtocol
from ghconcat.processing.lang_support.py_docstrip import strip_comments_and_docstrings
from ghconcat.processing.lang_support.dart_docstrip import strip_dart_comments
from ghconcat.utils.suffixes import compute_suffix_filters, is_suffix_allowed
from ghconcat.utils.paths import is_hidden_path, is_within_dir


class WalkerAppender(WalkerProtocol):
    """File concatenation and pre-processing pipeline.

    Responsibilities:
      * Discover files under given roots honoring include/exclude suffix filters.
      * Prepare file bodies (slicing, cleaning, comment/document stripping).
      * Concatenate into a single text result, optionally wrapping segments.

    Design notes:
      * All heavy-lifting operations are injected (read/slice/clean/apply),
        keeping this class cohesive and testable.
    """

    def __init__(
        self,
        *,
        read_file_as_lines,
        apply_replacements,
        slice_lines,
        clean_lines,
        header_delim: str,
        seen_files: Set[str],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._read_file_as_lines = read_file_as_lines
        self._apply_replacements = apply_replacements
        self._slice = slice_lines
        self._clean = clean_lines
        self._HEADER_DELIM = header_delim
        self._SEEN_FILES = seen_files
        self._log = logger or logging.getLogger("ghconcat.walker")

    # --------------------------------------------------------------------- #
    # Discovery
    # --------------------------------------------------------------------- #
    def gather_files(
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Collect files from 'add_path' honoring exclude lists & suffix filters."""
        collected: Set[Path] = set()
        explicit_files = [p for p in add_path if p.is_file()]
        dir_paths = [p for p in add_path if not p.is_file()]

        inc_set, exc_set = compute_suffix_filters(suffixes, exclude_suf)
        ex_dirs = {d.resolve() for d in exclude_dirs}

        def _dir_excluded(path: Path) -> bool:
            return any((is_within_dir(path, ex) for ex in ex_dirs))

        for fp in explicit_files:
            collected.add(fp.resolve())

        for root in dir_paths:
            if not root.exists():
                self._log.error("⚠  %s does not exist – skipped", root)
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip hidden dirs and excluded dirs early
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not d.startswith(".") and (not _dir_excluded(Path(dirpath, d)))
                ]
                for fn in filenames:
                    fp = Path(dirpath, fn)
                    if is_hidden_path(fp) or _dir_excluded(fp):
                        continue
                    if not is_suffix_allowed(fp.name, inc_set, exc_set):
                        continue
                    if fp.name.endswith((".pyc", ".pyo")):
                        continue
                    collected.add(fp.resolve())

        return sorted(collected, key=str)

    # --------------------------------------------------------------------- #
    # Preparation & Concatenation
    # --------------------------------------------------------------------- #
    def _prepare_body_lines(
        self, *, raw_lines: List[str], ns: argparse.Namespace, ext: str, file_path: Path
    ) -> List[str]:
        """Apply comment/doc stripping, cleaning & slicing to a file body."""
        lines: List[str] = list(raw_lines)

        rm_enabled: bool = self.should_remove_comments(ns)
        if rm_enabled:
            if ext == ".py":
                src = "".join(lines)
                stripped = strip_comments_and_docstrings(
                    src, language="py", filename=str(file_path)
                )
                lines = stripped.splitlines(True)
            elif ext == ".dart":
                src = "".join(lines)
                stripped = strip_dart_comments(src)
                lines = stripped.splitlines(True)
            else:
                lines = self._clean(
                    lines,
                    ext,
                    rm_comments=True,
                    no_rm_comments=True,
                    rm_imp=False,
                    rm_exp=False,
                    keep_blank=True,
                )

        if getattr(ns, "rm_import", False) or getattr(ns, "rm_export", False):
            lines = self._clean(
                lines,
                ext,
                rm_comments=False,
                no_rm_comments=False,
                rm_imp=getattr(ns, "rm_import", False),
                rm_exp=getattr(ns, "rm_export", False),
                keep_blank=True,
            )

        lines = self._clean(
            lines,
            ext,
            rm_comments=False,
            no_rm_comments=False,
            rm_imp=False,
            rm_exp=False,
            keep_blank=getattr(ns, "keep_blank", True),
        )

        lines = self._slice(
            lines,
            getattr(ns, "first_line", None),
            getattr(ns, "total_lines", None),
            getattr(ns, "keep_header", False),
        )
        return lines

    def concat_files(
        self,
        files: List[Path],
        ns: argparse.Namespace,
        *,
        header_root: Path,
        wrapped: Optional[List[Tuple[str, str]]] = None,
    ) -> str:
        """Concatenate processed files into a single string (optionally wrapped)."""
        parts: List[str] = []

        for idx, fp in enumerate(files):
            ext = fp.suffix.lower()
            raw_lines = self._read_file_as_lines(fp)

            if ns.list_only:
                rel = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)
                parts.append(rel + "\n")
                continue

            body_lines = self._prepare_body_lines(
                raw_lines=raw_lines, ns=ns, ext=ext, file_path=fp
            )
            if not body_lines or not "".join(body_lines).strip():
                continue

            hdr_path = str(fp) if ns.absolute_path else os.path.relpath(fp, header_root)

            if (not ns.skip_headers) and (hdr_path not in self._SEEN_FILES):
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

            # Keep a trailing newline between files unless the slice ended exactly.
            if ns.keep_blank and (
                idx < len(files) - 1
                or (idx == len(files) - 1 and ns.total_lines is None and (ns.first_line is None))
            ):
                parts.append("\n")

        return "".join(parts)

    # --------------------------------------------------------------------- #
    # Static utilities
    # --------------------------------------------------------------------- #
    @staticmethod
    def should_remove_comments(ns: Any) -> bool:
        """True if comment removal is effectively enabled for the current flags.

        Mirrors the legacy module-level behavior while living close to its only
        caller, improving cohesion.

        Args:
            ns: Namespace-like object (argparse.Namespace or compatible).

        Returns:
            True if simple comment removal should be applied.
        """
        return bool(getattr(ns, "rm_comments", False)) and (
            not bool(getattr(ns, "no_rm_comments", False))
        )
