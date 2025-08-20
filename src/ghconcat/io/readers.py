import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ghconcat.io.pdf_reader import PdfTextExtractor
from ghconcat.io.excel_reader import ExcelTsvExporter
from ghconcat.core.models import ReaderHint


class FileReader(ABC):
    """Abstract file reader that returns the content as a list of lines."""

    @abstractmethod
    def read_lines(self, path: Path) -> List[str]:
        """Read and return lines for the given file path."""
        raise NotImplementedError


class DefaultTextReader(FileReader):
    """UTF-8 text reader with binary/Unicode error protection."""

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
    """PDF reader that falls back to OCR if configured and needed."""

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
    """Excel reader that exports sheets to TSV before returning lines."""

    def __init__(self, *, exporter: Optional[ExcelTsvExporter] = None, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers.excel")
        self._exporter = exporter or ExcelTsvExporter(logger=self._log)

    def read_lines(self, path: Path) -> List[str]:
        tsv = self._exporter.export_tsv(path)
        if not tsv:
            return []
        return [ln + "\n" for ln in tsv.splitlines()]


@dataclass(frozen=True)
class _Rule:
    reader: FileReader
    priority: int = 0
    suffixes: Optional[tuple[str, ...]] = None
    predicate: Optional[Callable[[Path], bool]] = None
    mimes: Optional[tuple[str, ...]] = None


class ReaderRegistry:
    """Registry mapping file suffixes / predicates to `FileReader` instances.

    The registry supports:
      - Static suffix mapping (e.g. `.txt` → DefaultTextReader)
      - Rule-based dispatch with priority, suffix/mime filters and predicates
      - Push/pop stack to use temporary overrides within a context
    """

    def __init__(self, default_reader: Optional[FileReader] = None) -> None:
        self._map: Dict[str, FileReader] = {}
        self._rules: List[_Rule] = []
        self._default: FileReader = default_reader or DefaultTextReader()
        self._stack: List[Tuple[Dict[str, FileReader], List[_Rule], FileReader]] = []

    def push(self) -> None:
        self._stack.append((self._map.copy(), list(self._rules), self._default))

    def pop(self) -> None:
        if not self._stack:
            return
        self._map, self._rules, self._default = self._stack.pop()

    def register(self, suffixes: Sequence[str], reader: FileReader) -> None:
        norm: tuple[str, ...] = tuple(((s if s.startswith(".") else f".{s}").lower() for s in suffixes))
        for key in norm:
            self._map[key] = reader

    def for_suffix(self, suffix: str) -> FileReader:
        return self._map.get(suffix.lower(), self._default)

    def read_lines(self, path: Path) -> List[str]:
        return self.read_lines_ex(path, hint=None)

    def read_lines_ex(self, path: Path, hint: Optional[ReaderHint] = None) -> List[str]:
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
        norm_suffixes: Optional[tuple[str, ...]] = None
        if suffixes:
            norm_suffixes = tuple(((s if s.startswith(".") else f".{s}").lower() for s in suffixes))
        norm_mimes: Optional[tuple[str, ...]] = tuple(mimes) if mimes else None
        self._rules.append(
            _Rule(reader=reader, priority=priority, suffixes=norm_suffixes, predicate=predicate, mimes=norm_mimes)
        )

    def register_temp(self, suffixes: Sequence[str], reader: FileReader) -> None:
        self.push()
        self.register(suffixes, reader)

    def restore(self) -> None:
        self.pop()

    def snapshot_suffix_mappings(self) -> Tuple[Dict[str, FileReader], FileReader]:
        return (dict(self._map), self._default)

    def clone_suffix_only(self) -> "ReaderRegistry":
        """Return a registry that copies only suffix→reader mappings."""
        cloned = ReaderRegistry(default_reader=self._default)
        for suffix, reader in self._map.items():
            cloned.register([suffix], reader)
        cloned.set_default(self._default)
        return cloned


_GLOBAL_REGISTRY: Optional[ReaderRegistry] = None


def get_global_reader_registry(logger: Optional[logging.Logger] = None) -> ReaderRegistry:
    """Global registry lazily initialized with sensible defaults (txt/pdf/xlsx)."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        log = logger or logging.getLogger("ghconcat.readers")
        reg = ReaderRegistry(default_reader=DefaultTextReader(logger=log))
        reg.register([".pdf"], PdfFileReader(logger=log))
        reg.register([".xls", ".xlsx"], ExcelFileReader(logger=log))
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY