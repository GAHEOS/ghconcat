import logging
from pathlib import Path
from typing import Optional

from ghconcat.logging.helpers import get_logger


class ExcelTsvExporter:
    def __init__(self, *, logger: Optional[logging.Logger] = None) -> None:
        self._log = logger or get_logger('io.excel')

    def export_tsv(self, xls_path: Path) -> str:
        try:
            import pandas as pd
            import io
        except ModuleNotFoundError:
            self._log.warning('✘ %s: install `pandas` to enable Excel support.', xls_path)
            return ''

        tsv_chunks: list[str] = []
        try:
            with pd.ExcelFile(xls_path) as xls:
                for sheet in xls.sheet_names:
                    try:
                        df = xls.parse(sheet, dtype=str)
                    except Exception as exc:
                        self._log.error('✘ %s: failed to parse sheet %s (%s).', xls_path, sheet, exc)
                        continue
                    buf = io.StringIO()
                    df.fillna('').to_csv(buf, sep='\t', index=False, header=True)
                    tsv_chunks.append(f'===== {sheet} =====\n{buf.getvalue().strip()}')
        except Exception as exc:
            self._log.error('✘ %s: failed to open Excel file (%s).', xls_path, exc)
            return ''

        return '\n\n'.join(tsv_chunks)