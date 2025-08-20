"""
ghconcat package public API.
"""
from typing import Callable, Optional, Set, Dict
from logging import Logger
import logging  # added for safe default logger

__version__ = "0.9.0"

from .core import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
    DefaultGitManagerFactory,
    DefaultUrlFetcherFactory,
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
    DefaultWalkerFactory,
    DefaultRendererFactory,
    DefaultPathResolverFactory,
)
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
from ghconcat.cli import (
    GhConcat,
    HEADER_DELIM,
    _call_openai,
    _perform_upgrade,
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
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.rendering.path_resolver import (
    PathResolverProtocol,
    DefaultPathResolver,
    WorkspaceAwarePathResolver,
)
from ghconcat.rendering.renderer import Renderer, RendererProtocol
from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.discovery.file_discovery import FileDiscovery
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.logging.factory import DefaultLoggerFactory

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
    "Renderer",
    "FileDiscovery",
    "DefaultPathResolver",
    "WorkspaceAwarePathResolver",
    "SingleBraceTemplateEngine",
    "TemplateEngineProtocol",
    "walker_builder",
    "renderer_factory",
    "file_discovery_factory",
    "path_resolver_factory",
    "WalkerFactoryProtocol",
    "RendererFactoryProtocol",
    "PathResolverFactoryProtocol",
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
    "DefaultLoggerFactory",
]


def _interpolate(tpl: str, variables: Dict[str, str]) -> str:
    """Legacy-friendly single-brace interpolation helper.
    This tiny helper preserves the historical public surface by exposing a
    function-level API that delegates to :class:`SingleBraceTemplateEngine`.
    It performs **no** global caching and keeps **no** shared state to avoid
    cross-call surprises.
    """
    engine = SingleBraceTemplateEngine()
    return engine.render(tpl, variables)


def walker_builder(
        *,
        read_file_as_lines: Callable,
        apply_replacements: Callable[[str, Optional[list[str]], Optional[list[str]]], str],
        slice_lines: Callable[[list[str], Optional[int], Optional[int], bool], list[str]],
        clean_lines: Callable[..., list[str]],
        header_delim: str = HEADER_DELIM,
        seen_files: Optional[Set[str]] = None,
        logger: Optional[Logger] = None,
) -> WalkerAppender:
    """Return a configured :class:`WalkerAppender` delegating via DefaultWalkerFactory.
    This helper keeps a tiny API surface to instantiate a Walker compatible
    with :class:`WalkerProtocol` without importing internals from callers.
    Internally it uses the standard :class:`DefaultWalkerFactory` to ensure
    a single construction pathway across the app.
    """
    # Minimal FileReadingService-like adapter to honor factory signature
    class _FRSLite:
        def __init__(self, fn: Callable) -> None:
            self._fn = fn

        def read_lines(self, path):
            return self._fn(path)

    factory = DefaultWalkerFactory()
    lg = logger or logging.getLogger("ghconcat")
    return factory(
        file_reader_service=_FRSLite(read_file_as_lines),
        apply_replacements=apply_replacements,
        slice_lines=slice_lines,
        clean_lines=clean_lines,
        header_delim=header_delim,
        seen_files=seen_files or set(),
        logger=lg,
    )


def renderer_factory(
        *,
        walker,
        template_engine: Optional[TemplateEngineProtocol] = None,
        header_delim: str = HEADER_DELIM,
        logger: Optional[Logger] = None,
) -> Renderer:
    """Return a :class:`Renderer` using the default Renderer factory."""
    engine = template_engine or SingleBraceTemplateEngine(logger=logger)
    factory = DefaultRendererFactory()
    lg = logger or logging.getLogger("ghconcat")
    return factory(
        walker=walker,
        template_engine=engine,
        header_delim=header_delim,
        logger=lg,
    )


def path_resolver_factory(
        *,
        workspace: Optional[str] = None,
) -> WorkspaceAwarePathResolver:
    """Return a workspace-aware path resolver built via DefaultPathResolverFactory.
    The factory is parameterized to inject the optional *workspace* into the
    resulting :class:`WorkspaceAwarePathResolver`.
    """
    from pathlib import Path as _P  # local, explicit import

    ws = _P(workspace) if workspace else None
    factory = DefaultPathResolverFactory(builder=lambda: WorkspaceAwarePathResolver(workspace=ws))
    return factory()


def file_discovery_factory(
        *,
        walker,
        resolver: Optional[PathResolverProtocol] = None,
        git_manager_factory: Optional[DefaultGitManagerFactory] = None,
        url_fetcher_factory: Optional[DefaultUrlFetcherFactory] = None,
        logger: Optional[Logger] = None,
) -> FileDiscovery:
    """Return a :class:`FileDiscovery` with sensible defaults.
    This helper wires discovery using the same factories as runtime wiring,
    minimizing duplication while keeping the public API stable.
    """
    res = resolver or WorkspaceAwarePathResolver()
    gm = git_manager_factory or DefaultGitManagerFactory(lambda ws: GitRepositoryManager(ws, logger=logger))
    uf = url_fetcher_factory or DefaultUrlFetcherFactory(lambda ws: UrlFetcher(ws, logger=logger))
    return FileDiscovery(
        walker=walker,
        git_manager_factory=gm,
        url_fetcher_factory=uf,
        resolver=res,
        logger=logger,
    )