import logging
from pathlib import Path
from typing import Optional


class PdfTextExtractor:
    """Robust PDF → plaintext extractor with optional OCR fallback.

    This class mirrors the original ghconcat PDF extraction behavior:
    1) Try embedded text via ``pypdf.PdfReader``.
    2) If empty and *ocr_if_empty* is True, attempt OCR using
       ``pdf2image.convert_from_path`` + ``pytesseract``.
    3) If optional dependencies are missing, log a WARNING and return ``""``.

    Parameters
    ----------
    logger:
        Optional logger instance; a module logger is used by default.
    ocr_if_empty:
        When True, perform OCR only if no embedded text is found.
    dpi:
        Resolution used for rasterization during OCR.
    """

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        ocr_if_empty: bool = True,
        dpi: int = 300,
    ) -> None:
        self._log = logger or logging.getLogger("ghconcat.pdf")
        self._ocr_if_empty = ocr_if_empty
        self._dpi = dpi

    def extract_text(self, pdf_path: Path) -> str:
        """Return the full plaintext contents of *pdf_path*.

        The method keeps log messages and error handling aligned with the
        legacy implementation so that external behavior and tests remain
        fully compatible.

        Parameters
        ----------
        pdf_path:
            Absolute or relative path to a PDF file.

        Returns
        -------
        str
            Extracted text (possibly empty on failure or missing deps).
        """
        try:
            from pypdf import PdfReader  # type: ignore
        except ModuleNotFoundError:
            self._log.warning("✘ %s: install `pypdf` to enable PDF support.", pdf_path)
            return ""

        try:
            reader = PdfReader(pdf_path)
        except Exception as exc:  # noqa: BLE001
            self._log.error("✘ %s: failed to open PDF (%s).", pdf_path, exc)
            return ""

        pages_text: list[str] = []
        for idx, page in enumerate(reader.pages, start=1):
            txt = page.extract_text() or ""
            pages_text.append(txt.strip())
            self._log.debug("PDF %s  · page %d → %d chars", pdf_path.name, idx, len(txt))

        full = "\n\n".join(pages_text).strip()
        if full or not self._ocr_if_empty:
            if not full:
                self._log.warning("⚠ %s: no embedded text found.", pdf_path)
            return full

        try:
            from pdf2image import convert_from_path  # type: ignore
            import pytesseract  # type: ignore
        except ModuleNotFoundError:
            self._log.warning("✘ %s: OCR unavailable (pdf2image/pytesseract missing).", pdf_path)
            return ""

        self._log.info("⏳ OCR (%d pages) → %s", len(reader.pages), pdf_path.name)
        try:
            images = convert_from_path(pdf_path, dpi=self._dpi)
            ocr_chunks = [pytesseract.image_to_string(img) for img in images]
            return "\n\n".join(chunk.strip() for chunk in ocr_chunks)
        except Exception as exc:  # noqa: BLE001
            self._log.error("✘ OCR failed for %s (%s).", pdf_path, exc)
            return ""