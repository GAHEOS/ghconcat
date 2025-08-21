from __future__ import annotations

"""
Unified reader registry and built-in file readers.

This module exposes:
  * `ReaderRegistry`: A registry that maps suffixes and ad-hoc rules to readers.
  * `DefaultTextReader`, `PdfFileReader`, `ExcelFileReader`: Built-in readers.
  * `get_global_reader_registry`: Process-wide registry (suffix-only snapshot).
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ghconcat.io.pdf_reader import PdfTextExtractor
from ghconcat.io.excel_reader import ExcelTsvExporter
from ghconcat.core.models import ReaderHint


class FileReader(ABC):
    """Abstract interface for line-oriented file readers."""

    @abstractmethod
    def read_lines(self, path: Path) -> List[str]:
        """Read a file and return a list of lines (with newline characters)."""
        raise NotImplementedError


class DefaultTextReader(FileReader):
    """UTF-8 text reader with tolerant error handling."""

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers")

    def read_lines(self, path: Path) -> List[str]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            return content.splitlines(True)
        except UnicodeDecodeError:
            self._log.warning("✘ %s: binary or non-UTF-8 file skipped.", path)
            return []
        except Exception as exc:
            self._log.error("⚠  could not read %s (%s)", path, exc)
            return []


class PdfFileReader(FileReader):
    """PDF reader backed by `PdfTextExtractor` (with optional OCR)."""

    def __init__(
        self,
        *,
        extractor: Optional[PdfTextExtractor] = None,
        logger: Optional[logging.Logger] = None,
        ocr_if_empty: bool = True,
        dpi: int = 300,
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers.pdf")
        self._extractor = extractor or PdfTextExtractor(
            logger=self._log, ocr_if_empty=ocr_if_empty, dpi=dpi
        )

    def read_lines(self, path: Path) -> List[str]:
        text = self._extractor.extract_text(path)
        if not text:
            return []
        return [ln + "\n" for ln in text.splitlines()]


class ExcelFileReader(FileReader):
    """Excel reader that exports worksheets as TSV blocks."""

    def __init__(
        self,
        *,
        exporter: Optional[ExcelTsvExporter] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers.excel")
        self._exporter = exporter or ExcelTsvExporter(logger=self._log)

    def read_lines(self, path: Path) -> List[str]:
        tsv = self._exporter.export_tsv(path)
        if not tsv:
            return []
        return [ln + "\n" for ln in tsv.splitlines()]


@dataclass(frozen=True)
class _Rule:
    """Internal rule slot used by `ReaderRegistry`."""
    reader: FileReader
    priority: int = 0
    suffixes: Optional[tuple[str, ...]] = None
    predicate: Optional[Callable[[Path], bool]] = None
    mimes: Optional[tuple[str, ...]] = None


class ReaderRegistry:
    """Suffix and rule-based multiplexer of file readers.

    The registry supports:
      * Direct suffix mappings via `register(['.py'], reader)`.
      * Rules with optional suffix filters, predicates and MIME guards.
      * A stack-based push/pop for temporary overrides (used by HTML mode).
    """

    def __init__(self, default_reader: Optional[FileReader] = None) -> None:
        self._map: Dict[str, FileReader] = {}
        self._rules: List[_Rule] = []
        self._default: FileReader = default_reader or DefaultTextReader()
        # Push/pop snapshots contain (suffix_map, rules, default_reader).
        self._stack: List[Tuple[Dict[str, FileReader], List[_Rule], FileReader]] = []

    # ---- stack management ----

    def push(self) -> None:
        """Save current mappings and default reader onto the stack."""
        self._stack.append((self._map.copy(), list(self._rules), self._default))

    def pop(self) -> None:
        """Restore the previous snapshot from the stack if present."""
        if not self._stack:
            return
        self._map, self._rules, self._default = self._stack.pop()

    # ---- registration ----

    def register(self, suffixes: Sequence[str], reader: FileReader) -> None:
        """Register `reader` for each suffix in `suffixes`."""
        norm: tuple[str, ...] = tuple(
            ((s if s.startswith(".") else f".{s}").lower() for s in suffixes)
        )
        for key in norm:
            self._map[key] = reader

    def for_suffix(self, suffix: str) -> FileReader:
        """Return the reader mapped to `suffix` or the default one."""
        return self._map.get(suffix.lower(), self._default)

    # ---- reading ----

    def read_lines(self, path: Path) -> List[str]:
        """Read file using rules (if any) or fallback to suffix mapping."""
        return self.read_lines_ex(path, hint=None)

    def read_lines_ex(self, path: Path, hint: Optional[ReaderHint] = None) -> List[str]:
        """Read file with extra hints (e.g., MIME), using the best matching rule."""
        if self._rules:
            for rule in sorted(
                (r for r in self._rules if r.predicate is not None or r.suffixes or r.mimes),
                key=lambda r: r.priority,
                reverse=True,
            ):
                if rule.suffixes and path.suffix.lower() not in rule.suffixes:
                    continue
                if hint and rule.mimes and hint.mime and (hint.mime not in rule.mimes):
                    continue
                if rule.predicate and (not rule.predicate(path)):
                    continue
                return rule.reader.read_lines(path)
        return self.for_suffix(path.suffix).read_lines(path)

    # ---- defaults & rules ----

    @property
    def default_reader(self) -> FileReader:
        """Return the default reader."""
        return self._default

    def set_default(self, reader: FileReader) -> None:
        """Set a new default reader."""
        self._default = reader

    def register_rule(
        self,
        *,
        reader: FileReader,
        priority: int = 0,
        suffixes: Optional[Sequence[str]] = None,
        predicate: Optional[Callable[[Path], bool]] = None,
        mimes: Optional[Sequence[str]] = None,
    ) -> None:
        """Register a selection rule with optional filters and priority."""
        norm_suffixes: Optional[tuple[str, ...]] = None
        if suffixes:
            norm_suffixes = tuple(((s if s.startswith(".") else f".{s}").lower() for s in suffixes))
        norm_mimes: Optional[tuple[str, ...]] = tuple(mimes) if mimes else None
        self._rules.append(
            _Rule(reader=reader, priority=priority, suffixes=norm_suffixes, predicate=predicate, mimes=norm_mimes)
        )

    # ---- convenience helpers ----

    def register_temp(self, suffixes: Sequence[str], reader: FileReader) -> None:
        """Push current mappings and register a temporary mapping for suffixes."""
        self.push()
        self.register(suffixes, reader)

    def restore(self) -> None:
        """Pop a previously pushed snapshot."""
        self.pop()

    def snapshot_suffix_mappings(self) -> Tuple[Dict[str, FileReader], FileReader]:
        """Return a copy of the suffix map and the default reader."""
        return (dict(self._map), self._default)

    def clone_suffix_only(self) -> "ReaderRegistry":
        """Create a new registry carrying suffix mappings and default reader only."""
        cloned = ReaderRegistry(default_reader=self._default)
        for suffix, reader in self._map.items():
            cloned.register([suffix], reader)
        cloned.set_default(self._default)
        return cloned


_GLOBAL_REGISTRY: Optional[ReaderRegistry] = None


def get_global_reader_registry(logger: Optional[logging.Logger] = None) -> ReaderRegistry:
    """Return (and lazily initialize) the process-global reader registry.

    The global registry is used as a template; per-run registries clone its
    suffix mappings to avoid cross-run mutations.
    """
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        log = logger or logging.getLogger("ghconcat.readers")
        reg = ReaderRegistry(default_reader=DefaultTextReader(logger=log))
        reg.register([".pdf"], PdfFileReader(logger=log))
        reg.register([".xls", ".xlsx"], ExcelFileReader(logger=log))
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY