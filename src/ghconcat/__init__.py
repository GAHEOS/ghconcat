"""
ghconcat package public API.
"""
from .core import GitRepositoryManagerProtocol, GitManagerFactoryProtocol
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher, UrlFetcherProtocol, UrlFetcherFactoryProtocol
from ghconcat.cli import (  # type: ignore
    GhConcat,
    HEADER_DELIM,
    _call_openai,
    _perform_upgrade,
    _interpolate
)
from ghconcat.io.pdf_reader import PdfTextExtractor
from ghconcat.io.excel_reader import ExcelTsvExporter
from ghconcat.io.walker import WalkerAppender
from ghconcat.io.readers import (
    FileReader,
    ReaderRegistry,
    get_global_reader_registry,
    DefaultTextReader,
    PdfFileReader,
    ExcelFileReader,
)
from ghconcat.io.html_reader import HtmlToTextReader
from ghconcat.ai.ai_client import OpenAIClient
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.processing.envctx import EnvContext
from ghconcat.rendering.execution import ExecutionEngine  # existing export

from ghconcat.rendering.path_resolver import PathResolverProtocol
from ghconcat.rendering.renderer import RendererProtocol
from ghconcat.ai.ai_processor import AIProcessorProtocol
from ghconcat.io.file_reader_service import FileReadingService  # existing export

from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.comment_rules import COMMENT_RULES  # <- new public export

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
    "ExecutionEngine",
    "PathResolverProtocol",
    "RendererProtocol",
    "AIProcessorProtocol",
    "GitRepositoryManagerProtocol",
    "GitManagerFactoryProtocol",
    "UrlFetcherProtocol",
    "UrlFetcherFactoryProtocol",
    "FileReadingService",
    "LineProcessingService",
    "StringInterpolator",
    "_perform_upgrade",
    "_interpolate",
    "COMMENT_RULES",
]
__version__ = "2.0.0"
