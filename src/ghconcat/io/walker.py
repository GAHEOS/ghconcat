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
    """Concatenates files after walking directories and applying line-level transforms.

    This implementation keeps behavior compatible with existing tests while
    reducing duplication and improving readability.
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

    def gather_files(
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        """Collect files matching suffix rules while honoring hidden/exclude lists."""
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
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".") and (not _dir_excluded(Path(dirpath, d)))
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

    # ---------------------------
    # Internal cleaning pipeline
    # ---------------------------
    def _apply_cleaning_pipeline(
        self,
        *,
        raw_lines: List[str],
        ns: argparse.Namespace,
        ext: str,
        file_path: Path,
    ) -> List[str]:
        """Apply the full cleaning pipeline (comments/import/export/blank) preserving behavior.

        The sequence matches the previous logic to ensure test compatibility:
        1) Strip comments (language-specific if available).
        2) Conditionally remove import/export lines.
        3) Apply generic clean pass (blank line handling).
        """
        lines: List[str] = list(raw_lines)

        # 1) Comments removal (language-aware where possible).
        rm_enabled: bool = self.should_remove_comments(ns)
        if rm_enabled:
            if ext == ".py":
                src = "".join(lines)
                stripped = strip_comments_and_docstrings(src, language="py", filename=str(file_path))
                lines = stripped.splitlines(True)
            elif ext == ".dart":
                src = "".join(lines)
                stripped = strip_dart_comments(src)
                lines = stripped.splitlines(True)
            else:
                # Non-language-specific comment removal via line rules
                lines = self._clean(
                    lines,
                    ext,
                    rm_comments=True,
                    no_rm_comments=True,
                    rm_imp=False,
                    rm_exp=False,
                    keep_blank=True,
                )

        # 2) Import / export removal if requested.
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

        # 3) Final cleaning pass for blank line policy (keep/strip).
        lines = self._clean(
            lines,
            ext,
            rm_comments=False,
            no_rm_comments=False,
            rm_imp=False,
            rm_exp=False,
            keep_blank=getattr(ns, "keep_blank", True),
        )
        return lines

    def _prepare_body_lines(
        self,
        *,
        raw_lines: List[str],
        ns: argparse.Namespace,
        ext: str,
        file_path: Path,
    ) -> List[str]:
        """Prepare file body lines by applying the cleaning pipeline and slicing."""
        # Apply the unified cleaning pipeline
        lines = self._apply_cleaning_pipeline(raw_lines=raw_lines, ns=ns, ext=ext, file_path=file_path)
        # Slice after cleaning to preserve previous semantics
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
        """Concatenate files, optionally collecting wrapped bodies for code fences."""
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
                    and (ns.first_line is None)
                )
            ):
                parts.append("\n")
        return "".join(parts)

    @staticmethod
    def should_remove_comments(ns: Any) -> bool:
        """Return True when comment removal is active."""
        return bool(getattr(ns, "rm_comments", False)) and (
            not bool(getattr(ns, "no_rm_comments", False))
        )