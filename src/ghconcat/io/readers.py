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
from ghconcat.utils.suffixes import normalize_suffixes  # ← reuse shared helper


class FileReader(ABC):
    @abstractmethod
    def read_lines(self, path: Path) -> List[str]:
        raise NotImplementedError


class DefaultTextReader(FileReader):
    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger('ghconcat.readers')

    def read_lines(self, path: Path) -> List[str]:
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            return content.splitlines(True)
        except UnicodeDecodeError:
            self._log.warning('✘ %s: binary or non-UTF-8 file skipped.', path)
            return []
        except Exception as exc:
            self._log.error('⚠  could not read %s (%s)', path, exc)
            return []


class PdfFileReader(FileReader):
    def __init__(
            self,
            *,
            extractor: Optional[PdfTextExtractor] = None,
            logger: Optional[logging.Logger] = None,
            ocr_if_empty: bool = True,
            dpi: int = 300,
    ) -> None:
        self._log = logger or logging.getLogger('ghconcat.readers.pdf')
        self._extractor = extractor or PdfTextExtractor(logger=self._log, ocr_if_empty=ocr_if_empty, dpi=dpi)

    def read_lines(self, path: Path) -> List[str]:
        text = self._extractor.extract_text(path)
        if not text:
            return []
        return [ln + (''
                      '') for ln in text.splitlines()]


class ExcelFileReader(FileReader):
    def __init__(self, *, exporter: Optional[ExcelTsvExporter] = None, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger('ghconcat.readers.excel')
        self._exporter = exporter or ExcelTsvExporter(logger=self._log)

    def read_lines(self, path: Path) -> List[str]:
        tsv = self._exporter.export_tsv(path)
        if not tsv:
            return []
        return [ln + '\n' for ln in tsv.splitlines()]


@dataclass(frozen=True)
class _Rule:
    reader: FileReader
    priority: int = 0
    suffixes: Optional[tuple[str, ...]] = None
    predicate: Optional[Callable[[Path], bool]] = None
    mimes: Optional[tuple[str, ...]] = None


class ReaderRegistry:
    def __init__(self, default_reader: Optional[FileReader] = None) -> None:
        self._map: Dict[str, FileReader] = {}
        self._rules: List[_Rule] = []
        self._default: FileReader = default_reader or DefaultTextReader()
        self._stack: List[Tuple[Dict[str, FileReader], List[_Rule], FileReader]] = []
        self._rules_sorted_cache: List[_Rule] | None = None

    def _invalidate_cache(self) -> None:
        self._rules_sorted_cache = None

    def _get_sorted_rules(self) -> List[_Rule]:
        if self._rules_sorted_cache is not None:
            return self._rules_sorted_cache
        candidates = [r for r in self._rules if r.predicate is not None or r.suffixes or r.mimes]
        self._rules_sorted_cache = sorted(candidates, key=lambda r: r.priority, reverse=True)
        return self._rules_sorted_cache

    def push(self) -> None:
        self._stack.append((self._map.copy(), list(self._rules), self._default))

    def pop(self) -> None:
        if not self._stack:
            return
        self._map, self._rules, self._default = self._stack.pop()
        self._invalidate_cache()

    def register(self, suffixes: Sequence[str], reader: FileReader) -> None:
        """Register a reader for given suffixes (case-insensitive).

        We normalize with `normalize_suffixes` and then lower-case to preserve
        the previous behavior of case-insensitive matching.
        """
        norm = [s.lower() for s in normalize_suffixes(suffixes)]
        for key in norm:
            self._map[key] = reader

    def for_suffix(self, suffix: str) -> FileReader:
        return self._map.get(suffix.lower(), self._default)

    def read_lines(self, path: Path) -> List[str]:
        return self.read_lines_ex(path, hint=None)

    def read_lines_ex(self, path: Path, hint: Optional[ReaderHint] = None) -> List[str]:
        for rule in self._get_sorted_rules():
            if rule.suffixes and path.suffix.lower() not in rule.suffixes:
                continue
            if hint and rule.mimes and hint.mime and (hint.mime not in rule.mimes):
                continue
            if rule.predicate and (not rule.predicate(path)):
                continue
            return rule.reader.read_lines(path)
        return self.for_suffix(path.suffix).read_lines(path)

    @property
    def default_reader(self) -> FileReader:
        return self._default

    def set_default(self, reader: FileReader) -> None:
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
        """Register an advanced rule with optional suffix/mime filters."""
        norm_suffixes: Optional[tuple[str, ...]] = None
        if suffixes:
            norm_suffixes = tuple(s.lower() for s in normalize_suffixes(suffixes))
        norm_mimes: Optional[tuple[str, ...]] = tuple(mimes) if mimes else None
        self._rules.append(
            _Rule(reader=reader, priority=priority, suffixes=norm_suffixes, predicate=predicate, mimes=norm_mimes))
        self._invalidate_cache()

    def snapshot_suffix_mappings(self) -> Tuple[Dict[str, FileReader], FileReader]:
        return (dict(self._map), self._default)

    def clone_suffix_only(self) -> 'ReaderRegistry':
        cloned = ReaderRegistry(default_reader=self._default)
        for suffix, reader in self._map.items():
            cloned.register([suffix], reader)
        cloned.set_default(self._default)
        return cloned


_GLOBAL_REGISTRY: Optional[ReaderRegistry] = None


def get_global_reader_registry(logger: Optional[logging.Logger] = None) -> ReaderRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        log = logger or logging.getLogger('ghconcat.readers')
        reg = ReaderRegistry(default_reader=DefaultTextReader(logger=log))
        reg.register(['.pdf'], PdfFileReader(logger=log))
        reg.register(['.xls', '.xlsx'], ExcelFileReader(logger=log))
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY
