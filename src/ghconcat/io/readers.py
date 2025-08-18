import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ghconcat.io.pdf_reader import PdfTextExtractor
from ghconcat.io.excel_reader import ExcelTsvExporter


class FileReader(ABC):
    """Abstract file reader that returns a file body as text lines.

    Implementations must always return a list of *text* lines ending with a
    newline character ('\\n'), suitable for direct concatenation.

    Notes
    -----
    • Implementations should never raise for non-text/binary files; they must
      return an empty list when the content cannot be decoded or is unsupported.
    """

    @abstractmethod
    def read_lines(self, path: Path) -> List[str]:
        """Return file contents as a list of lines terminated with '\\n'."""
        raise NotImplementedError


class DefaultTextReader(FileReader):
    """UTF‑8 text reader with 'ignore' error handling.

    This matches the legacy ghconcat behavior for generic files:
      • Reads with UTF-8 and `errors="ignore"`.
      • Universal newlines normalize CRLF to LF.
      • Returns `[]` only if a `UnicodeDecodeError` is ever raised (defensive).
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.readers")

    def read_lines(self, path: Path) -> List[str]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            return content.splitlines(True)
        except UnicodeDecodeError:
            self._log.warning("✘ %s: binary or non-UTF-8 file skipped.", path)
            return []
        except Exception as exc:  # noqa: BLE001
            self._log.error("⚠  could not read %s (%s)", path, exc)
            return []


class PdfFileReader(FileReader):
    """PDF → text reader built on top of :class:`PdfTextExtractor`."""

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
    """Excel (.xlsx/.xls) → TSV reader built on :class:`ExcelTsvExporter`."""

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
    """Internal rule used by the registry for predicate/priority matching."""
    reader: FileReader
    priority: int = 0
    suffixes: Optional[tuple[str, ...]] = None
    predicate: Optional[Callable[[Path], bool]] = None


class ReaderRegistry:
    """Multi-criteria registry of :class:`FileReader` implementations.

    The registry supports:
      • Suffix-based mapping ('.ext' or 'ext') – **backwards compatible**.
      • Optional *rules* with predicates and priority for more advanced
        matching (MIME, heuristics, etc.). Predicated rules take precedence
        over plain suffix mappings. Among predicated rules, higher-priority
        ones win; ties preserve insertion order.

    If no rule/mapping matches the file, the default reader is used.

    Parameters
    ----------
    default_reader:
        Reader used when no specific rule matches.
    """

    def __init__(self, default_reader: Optional[FileReader] = None) -> None:
        self._map: Dict[str, FileReader] = {}
        self._rules: List[_Rule] = []
        self._default: FileReader = default_reader or DefaultTextReader()
        # New: a stack of mapping snapshots to support push/pop scoped overrides
        self._stack: List[Tuple[Dict[str, FileReader], List[_Rule], FileReader]] = []

    def push(self) -> None:
        """Push the current mapping/rules/default onto an internal stack.

        This allows temporary overrides that can be safely reverted with `pop()`.
        """
        self._stack.append((self._map.copy(), list(self._rules), self._default))

    def pop(self) -> None:
        """Restore the last pushed mapping/rules/default.

        If the stack is empty, this is a no-op (defensive behavior).
        """
        if not self._stack:
            return
        self._map, self._rules, self._default = self._stack.pop()

    # Backwards-compatible registration API
    def register(self, suffixes: Sequence[str], reader: FileReader) -> None:
        """Register *reader* for every suffix in *suffixes* ('.ext' or 'ext').

        This updates the suffix→reader map (last registration wins) and also
        stores a *rule* with the same suffix set and default priority=0.
        """
        norm: tuple[str, ...] = tuple(
            (s if s.startswith(".") else f".{s}").lower() for s in suffixes
        )
        for key in norm:
            self._map[key] = reader
        self._rules.append(_Rule(reader=reader, priority=0, suffixes=norm))

    def for_suffix(self, suffix: str) -> FileReader:
        """Return the reader for *suffix* or the default reader."""
        return self._map.get(suffix.lower(), self._default)

    def read_lines(self, path: Path) -> List[str]:
        """Read *path* using the best-matching rule or the suffix map.

        Priority order:
          1) Predicated rules (highest priority first, ties by insertion).
          2) Suffix map resolution (last registration wins).
          3) Default reader.
        """
        if self._rules:
            for rule in sorted(
                (r for r in self._rules if r.predicate is not None),
                key=lambda r: r.priority,
                reverse=True,
            ):
                if rule.suffixes and path.suffix.lower() not in rule.suffixes:
                    continue
                if rule.predicate and not rule.predicate(path):
                    continue
                return rule.reader.read_lines(path)

        return self.for_suffix(path.suffix).read_lines(path)

    @property
    def default_reader(self) -> FileReader:
        """Return the default reader."""
        return self._default

    def set_default(self, reader: FileReader) -> None:
        """Set the default reader used for unmatched suffixes."""
        self._default = reader

    def register_rule(
        self,
        *,
        reader: FileReader,
        priority: int = 0,
        suffixes: Optional[Sequence[str]] = None,
        predicate: Optional[Callable[[Path], bool]] = None,
    ) -> None:
        """Register an advanced rule with optional suffix filter & predicate.

        Notes
        -----
        • Predicated rules take precedence over suffix map entries.
        • This method does not alter the suffix→reader map. Use `register()`
          to replace the reader for a suffix in a backwards compatible way.
        """
        norm: Optional[tuple[str, ...]] = None
        if suffixes:
            norm = tuple(
                (s if s.startswith(".") else f".{s}").lower() for s in suffixes
            )
        self._rules.append(
            _Rule(reader=reader, priority=priority, suffixes=norm, predicate=predicate)
        )

    # New: helper utilities for reversible temporary registrations
    def register_temp(self, suffixes: Sequence[str], reader: FileReader) -> None:
        """Push + register in a single call (temporary mapping).

        Use `restore()` to revert to the previous mapping.
        """
        self.push()
        self.register(suffixes, reader)

    def restore(self) -> None:
        """Revert the last `register_temp()` call."""
        self.pop()


_GLOBAL_REGISTRY: Optional[ReaderRegistry] = None


def get_global_reader_registry(
    logger: Optional[logging.Logger] = None,
) -> ReaderRegistry:
    """Return the process-wide reader registry, creating it on first use.

    The global registry is pre-populated with the built-in readers:

      • '.pdf'  → :class:`PdfFileReader`
      • '.xls', '.xlsx' → :class:`ExcelFileReader`
      • default → :class:`DefaultTextReader`

    Parameters
    ----------
    logger:
        Optional logger propagated to built-in readers (for homogeneous logs).

    Returns
    -------
    ReaderRegistry
        The singleton registry instance.
    """
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        log = logger or logging.getLogger("ghconcat.readers")
        reg = ReaderRegistry(default_reader=DefaultTextReader(logger=log))
        reg.register([".pdf"], PdfFileReader(logger=log))
        reg.register([".xls", ".xlsx"], ExcelFileReader(logger=log))
        _GLOBAL_REGISTRY = reg
    return _GLOBAL_REGISTRY