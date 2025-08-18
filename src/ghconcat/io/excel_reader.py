import logging
from pathlib import Path
from typing import Optional


class ExcelTsvExporter:
    """Excel → TSV exporter combining all sheets with sheet banners.

    Behavior matches ghconcat's legacy routine:
      • Requires ``pandas`` (and a valid Excel engine: openpyxl|xlrd|pyxlsb).
      • Each sheet is prefixed by: ``===== <sheet name> =====``.
      • Empty cells become empty strings to keep column alignment.
      • On any failure it logs and returns ``""`` (non-fatal).

    Parameters
    ----------
    logger:
        Optional logger instance; defaults to a module-specific logger.
    """

    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or logging.getLogger("ghconcat.excel")

    def export_tsv(self, xls_path: Path) -> str:
        """Return a TSV dump (all sheets) for *xls_path*.

        Parameters
        ----------
        xls_path:
            Path to an ``.xls`` or ``.xlsx`` file.

        Returns
        -------
        str
            Concatenated TSV of all sheets (may be empty string).
        """
        try:
            import pandas as pd  # type: ignore
            import io  # noqa: WPS433  (stdlib)
        except ModuleNotFoundError:
            self._log.warning("✘ %s: install `pandas` to enable Excel support.", xls_path)
            return ""

        tsv_chunks: list[str] = []
        try:
            with pd.ExcelFile(xls_path) as xls:
                for sheet in xls.sheet_names:
                    try:
                        df = xls.parse(sheet, dtype=str)  # force string representation
                    except Exception as exc:  # noqa: BLE001
                        self._log.error("✘ %s: failed to parse sheet %s (%s).", xls_path, sheet, exc)
                        continue

                    buf = io.StringIO()
                    df.fillna("").to_csv(buf, sep="\t", index=False, header=True)
                    tsv_chunks.append(f"===== {sheet} =====\n{buf.getvalue().strip()}")
        except Exception as exc:  # noqa: BLE001
            self._log.error("✘ %s: failed to open Excel file (%s).", xls_path, exc)
            return ""

        return "\n\n".join(tsv_chunks)