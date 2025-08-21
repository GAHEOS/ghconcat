from __future__ import annotations
import logging
from typing import Optional

from .core import (
    GitManagerFactoryProtocol,
    GitRepositoryManagerProtocol,
    PathResolverFactoryProtocol,
    RendererFactoryProtocol,
    UrlFetcherFactoryProtocol,
    UrlFetcherProtocol,
    WalkerFactoryProtocol,
    DefaultGitManagerFactory,
    DefaultPathResolverFactory,
    DefaultRendererFactory,
    DefaultWalkerFactory,
    DefaultUrlFetcherFactory,
)
from ghconcat.constants import HEADER_DELIM
from ghconcat.cli import GhConcat
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
from ghconcat.io.excel_reader import ExcelTsvExporter
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.io.html_reader import HtmlToTextReader
from ghconcat.io.pdf_reader import PdfTextExtractor
from ghconcat.io.readers import (
    DefaultTextReader,
    ExcelFileReader,
    FileReader,
    ReaderRegistry,
    get_global_reader_registry,
    PdfFileReader,
)
from ghconcat.io.walker import WalkerAppender
from ghconcat.ai.ai_client import OpenAIClient
from ghconcat.processing.comment_rules import COMMENT_RULES
from ghconcat.processing.envctx import EnvContext
from ghconcat.processing.line_ops import LineProcessingService
from ghconcat.processing.string_interpolator import StringInterpolator
from ghconcat.processing.text_ops import TextTransformer
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.rendering.path_resolver import (
    DefaultPathResolver,
    PathResolverProtocol,
    WorkspaceAwarePathResolver,
)
from ghconcat.rendering.renderer import Renderer, RendererProtocol
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.logging.factory import DefaultLoggerFactory
from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.discovery.file_discovery import FileDiscovery
from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.runtime.policies import DefaultPolicies
from ghconcat.runtime.runner import EngineRunner
from ghconcat.utils.net import ssl_context_for as _ssl_ctx_for
from ghconcat.parsing.parser import _build_parser
from ghconcat.runtime.sdk import _call_openai, _perform_upgrade
from ghconcat.logging.helpers import get_logger
from ghconcat.ai.model_registry import ModelSpec, get_registry, register_model

__version__ = '0.9.1'


def renderer_factory(
        *,
        walker,
        template_engine: Optional[TemplateEngineProtocol] = None,
        header_delim: str = HEADER_DELIM,
        logger: Optional[logging.Logger] = None,
) -> Renderer:
    """Factory helper to build a Renderer with sane defaults."""
    engine = template_engine or SingleBraceTemplateEngine(logger=logger)
    factory = DefaultRendererFactory()
    lg = logger or get_logger('render')
    return factory(walker=walker, template_engine=engine, header_delim=header_delim, logger=lg)


def path_resolver_factory(*, workspace: Optional[str] = None) -> WorkspaceAwarePathResolver:
    """Factory helper to build a PathResolver aware of a workspace."""
    from pathlib import Path as _P

    ws = _P(workspace) if workspace else None
    factory = DefaultPathResolverFactory(builder=lambda: WorkspaceAwarePathResolver(workspace=ws))
    return factory()


__all__ = [
    'GhConcat',
    'HEADER_DELIM',
    'WalkerAppender',
    'UrlFetcher',
    'PdfTextExtractor',
    'ExcelTsvExporter',
    'FileReader',
    'ReaderRegistry',
    'get_global_reader_registry',
    'DefaultTextReader',
    'PdfFileReader',
    'ExcelFileReader',
    'HtmlToTextReader',
    'OpenAIClient',
    'GitRepositoryManager',
    'TextTransformer',
    'EnvContext',
    'ExecutionEngine',
    'PathResolverProtocol',
    'RendererProtocol',
    'AIProcessorProtocol',
    'GitRepositoryManagerProtocol',
    'GitManagerFactoryProtocol',
    'UrlFetcherProtocol',
    'UrlFetcherFactoryProtocol',
    'FileReadingService',
    'LineProcessingService',
    'StringInterpolator',
    'COMMENT_RULES',
    'Renderer',
    'FileDiscovery',
    'DefaultPathResolver',
    'WorkspaceAwarePathResolver',
    'SingleBraceTemplateEngine',
    'TemplateEngineProtocol',
    'renderer_factory',
    'path_resolver_factory',
    'WalkerFactoryProtocol',
    'RendererFactoryProtocol',
    'PathResolverFactoryProtocol',
    'DefaultWalkerFactory',
    'DefaultRendererFactory',
    'DefaultPathResolverFactory',
    'DefaultLoggerFactory',
    'InputClassifierProtocol',
    'DefaultInputClassifier',
    'EngineBuilder',
    'EngineConfig',
    'DefaultPolicies',
    'EngineRunner',
    '_call_openai',
    '_perform_upgrade',
    '_build_parser',
    'ModelSpec',
    'get_registry',
    'register_model',
]
