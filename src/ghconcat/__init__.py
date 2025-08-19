"""
ghconcat package public API.
"""
from typing import Callable, Optional, Set
import logging

__version__ = "0.9.0"

from .core import (
    GitRepositoryManagerProtocol,
    GitManagerFactoryProtocol,
    UrlFetcherProtocol,
    UrlFetcherFactoryProtocol,
    DefaultGitManagerFactory,
    DefaultUrlFetcherFactory,
    # New DI items
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
    DefaultWalkerFactory,
    DefaultRendererFactory,
    DefaultPathResolverFactory,
)
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
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

from ghconcat.rendering.path_resolver import (
    PathResolverProtocol,
    DefaultPathResolver,
    WorkspaceAwarePathResolver,
)
from ghconcat.rendering.renderer import Renderer, RendererProtocol
from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.io.file_reader_service import FileReadingService  # existing export

from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.comment_rules import COMMENT_RULES  # <- new public export

from ghconcat.discovery.file_discovery import FileDiscovery
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.adapters import WalkerAdapter

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
    "WalkerAdapter",

    "walker_builder",
    "renderer_factory",
    "file_discovery_factory",
    "path_resolver_factory",

    # New DI items exposed at top-level
    "WalkerFactoryProtocol",
    "RendererFactoryProtocol",
    "PathResolverFactoryProtocol",
    "DefaultWalkerFactory",
    "DefaultRendererFactory",
    "DefaultPathResolverFactory",
]



def walker_builder(
    *,
    read_file_as_lines: Callable,
    apply_replacements: Callable[[str, Optional[list[str]], Optional[list[str]]], str],
    slice_lines: Callable[[list[str], Optional[int], Optional[int], bool], list[str]],
    clean_lines: Callable[..., list[str]],
    header_delim: str = HEADER_DELIM,
    seen_files: Optional[Set[str]] = None,
    logger: Optional[logging.Logger] = None,
) -> WalkerAppender:
    """Return a configured :class:`WalkerAppender`.

    This helper keeps a tiny API surface to instantiate a Walker compatible
    with :class:`WalkerProtocol` without importing internals from callers.
    """
    return WalkerAppender(
        read_file_as_lines=read_file_as_lines,
        apply_replacements=apply_replacements,
        slice_lines=slice_lines,
        clean_lines=clean_lines,
        header_delim=header_delim,
        seen_files=seen_files or set(),
        logger=logger,
    )


def renderer_factory(
    *,
    walker,
    template_engine: Optional[TemplateEngineProtocol] = None,
    header_delim: str = HEADER_DELIM,
    logger: Optional[logging.Logger] = None,
) -> Renderer:
    """Return a :class:`Renderer` using the given Walker and template engine."""
    engine = template_engine or SingleBraceTemplateEngine(logger=logger)
    return Renderer(
        walker=walker,
        template_engine=engine,
        header_delim=header_delim,
        logger=logger,
    )


def path_resolver_factory(
    *,
    workspace: Optional[str] = None,
) -> WorkspaceAwarePathResolver:
    """Return a workspace-aware path resolver."""
    ws = None if workspace is None else Path(workspace)  # type: ignore[name-defined]
    from pathlib import Path as _P  # noqa: N816
    ws = None if workspace is None else _P(workspace)
    return WorkspaceAwarePathResolver(workspace=ws)


def file_discovery_factory(
    *,
    walker,
    resolver: Optional[PathResolverProtocol] = None,
    git_manager_factory: Optional[DefaultGitManagerFactory] = None,
    url_fetcher_factory: Optional[DefaultUrlFetcherFactory] = None,
    logger: Optional[logging.Logger] = None,
) -> FileDiscovery:
    """Return a :class:`FileDiscovery` with sensible defaults."""
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