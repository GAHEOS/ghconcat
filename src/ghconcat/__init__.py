"""
ghconcat package public API.
"""
from __future__ import annotations

from .ghconcat import (  # type: ignore
    GhConcat,
    HEADER_DELIM,
    _call_openai,
    _perform_upgrade,
    _interpolate
)
from .pdf_reader import PdfTextExtractor
from .excel_reader import ExcelTsvExporter
from .walker import WalkerAppender
from .url_fetcher import UrlFetcher
from .readers import (
    FileReader,
    ReaderRegistry,
    get_global_reader_registry,
    DefaultTextReader,
    PdfFileReader,
    ExcelFileReader,
)
from .html_reader import HtmlToTextReader
from .ai_client import OpenAIClient
from .git_repository import GitRepositoryManager
from .textops import TextTransformer
from .envctx import EnvContext
from .execution import ExecutionEngine  # NEW export

__all__ = [
    "GhConcat",
    "HEADER_DELIM",
    "WalkerAppender",
    "UrlFetcher",
    "PdfTextExtractor",
    "ExcelTsvExporter",
    "FileReader",
    "ReaderRegistry",
    "get_global_reader_registry",
    "DefaultTextReader",
    "PdfFileReader",
    "ExcelFileReader",
    "HtmlToTextReader",
    "OpenAIClient",
    "GitRepositoryManager",
    "TextTransformer",
    "EnvContext",
    "ExecutionEngine",  # NEW
    "_perform_upgrade",
    "_interpolate"
]
__version__ = "2.0.0"