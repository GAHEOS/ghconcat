from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Set, Tuple

from ghconcat.ai.ai_processor import DefaultAIProcessor
from ghconcat.core import (
    DefaultGitManagerFactory,
    DefaultPathResolverFactory,
    DefaultRendererFactory,
    DefaultUrlFetcherFactory,
    DefaultWalkerFactory,
)
from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.core.interfaces.factories import (
    PathResolverFactoryProtocol,
    RendererFactoryProtocol,
    WalkerFactoryProtocol,
)
from ghconcat.core.interfaces.fs import FileDiscoveryProtocol, PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.discovery.file_discovery import FileDiscovery
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.io.readers import ReaderRegistry, get_global_reader_registry
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine


@dataclass(frozen=True)
class EngineConfig:
    """Declarative configuration container for building the ExecutionEngine."""

    logger: logging.Logger
    header_delim: str
    seen_files: Set[str]
    clones_cache: Dict[Tuple[str, Optional[str]], Path]
    workspaces_seen: Set[Path]
    ssl_ctx_provider: Callable[[str], Optional[object]]
    parser_factory: Callable[[], object]
    post_parse: Callable[[object], None]
    merge_ns: Callable[[object, object], object]
    expand_tokens: Callable[[list[str], Dict[str, str]], list[str]]
    parse_env_items: Callable[[Optional[list[str]]], Dict[str, str]]
    interpolate: Callable[[str, Dict[str, str]], str]
    apply_replacements: Callable[[str, Optional[list[str]], Optional[list[str]]], str]
    slice_lines: Callable[[list[str], Optional[int], Optional[int], bool], list[str]]
    clean_lines: Callable[..., list[str]]
    fatal: Callable[[str], None]

    # Optional factories
    walker_factory: Optional[WalkerFactoryProtocol] = None
    renderer_factory: Optional[RendererFactoryProtocol] = None
    discovery_factory: Optional[
        Callable[
            [WalkerProtocol, DefaultGitManagerFactory, DefaultUrlFetcherFactory, PathResolverProtocol, logging.Logger],
            FileDiscoveryProtocol,
        ]
    ] = None
    path_resolver_factory: Optional[PathResolverFactoryProtocol] = None

    # Optional strategy objects
    classifier: Optional[InputClassifierProtocol] = None


@dataclass
class EngineBuilder:
    """Imperative builder that can be constructed manually or via EngineConfig."""
    logger: logging.Logger
    header_delim: str
    seen_files: Set[str]
    clones_cache: Dict[Tuple[str, Optional[str]], Path]
    workspaces_seen: Set[Path]
    ssl_ctx_provider: Callable[[str], Optional[object]]
    parser_factory: Callable[[], object]
    post_parse: Callable[[object], None]
    merge_ns: Callable[[object, object], object]
    expand_tokens: Callable[[list[str], Dict[str, str]], list[str]]
    parse_env_items: Callable[[Optional[list[str]]], Dict[str, str]]
    interpolate: Callable[[str, Dict[str, str]], str]
    apply_replacements: Callable[[str, Optional[list[str]], Optional[list[str]]], str]
    slice_lines: Callable[[list[str], Optional[int], Optional[int], bool], list[str]]
    clean_lines: Callable[..., list[str]]
    fatal: Callable[[str], None]
    walker_factory: Optional[WalkerFactoryProtocol] = None
    renderer_factory: Optional[RendererFactoryProtocol] = None
    discovery_factory: Optional[
        Callable[
            [WalkerProtocol, DefaultGitManagerFactory, DefaultUrlFetcherFactory, PathResolverProtocol, logging.Logger],
            FileDiscoveryProtocol,
        ]
    ] = None
    path_resolver_factory: Optional[PathResolverFactoryProtocol] = None
    classifier: Optional[InputClassifierProtocol] = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "EngineBuilder":
        return cls(
            logger=cfg.logger,
            header_delim=cfg.header_delim,
            seen_files=cfg.seen_files,
            clones_cache=cfg.clones_cache,
            workspaces_seen=cfg.workspaces_seen,
            ssl_ctx_provider=cfg.ssl_ctx_provider,
            parser_factory=cfg.parser_factory,
            post_parse=cfg.post_parse,
            merge_ns=cfg.merge_ns,
            expand_tokens=cfg.expand_tokens,
            parse_env_items=cfg.parse_env_items,
            interpolate=cfg.interpolate,
            apply_replacements=cfg.apply_replacements,
            slice_lines=cfg.slice_lines,
            clean_lines=cfg.clean_lines,
            fatal=cfg.fatal,
            walker_factory=cfg.walker_factory,
            renderer_factory=cfg.renderer_factory,
            discovery_factory=cfg.discovery_factory,
            path_resolver_factory=cfg.path_resolver_factory,
            classifier=cfg.classifier,
        )

    def _clone_registry_for_run(self) -> ReaderRegistry:
        g = get_global_reader_registry(self.logger)
        return g.clone_suffix_only()

    def build(self, *, call_openai) -> ExecutionEngine:
        """Create a fully wired ExecutionEngine instance."""
        reg = self._clone_registry_for_run()
        frs = FileReadingService(registry=reg, logger=self.logger)

        pr_factory = self.path_resolver_factory or DefaultPathResolverFactory()
        w_factory = self.walker_factory or DefaultWalkerFactory()
        r_factory = self.renderer_factory or DefaultRendererFactory()

        resolver: PathResolverProtocol = pr_factory()
        walker: WalkerProtocol = w_factory(
            frs,
            self.apply_replacements,
            self.slice_lines,
            self.clean_lines,
            self.header_delim,
            self.seen_files,
            self.logger,
        )

        gm_factory = DefaultGitManagerFactory(lambda ws: GitRepositoryManager(ws, logger=self.logger, clones_cache=self.clones_cache))
        uf_factory = DefaultUrlFetcherFactory(lambda ws: UrlFetcher(ws, logger=self.logger, ssl_ctx_provider=self.ssl_ctx_provider))

        if self.discovery_factory is not None:
            discovery: FileDiscoveryProtocol = self.discovery_factory(walker, gm_factory, uf_factory, resolver, self.logger)
        else:
            discovery = FileDiscovery(
                walker=walker,
                git_manager_factory=gm_factory,
                url_fetcher_factory=uf_factory,
                resolver=resolver,
                logger=self.logger,
            )

        tpl_engine = SingleBraceTemplateEngine(logger=self.logger)
        renderer: RendererProtocol = r_factory(walker, tpl_engine, self.header_delim, self.logger)
        ai = DefaultAIProcessor(call_openai=call_openai, logger=self.logger)

        engine = ExecutionEngine(
            parser_factory=self.parser_factory,
            post_parse=self.post_parse,
            merge_ns=self.merge_ns,
            expand_tokens=self.expand_tokens,
            parse_env_items=self.parse_env_items,
            resolver=resolver,
            discovery=discovery,
            renderer=renderer,
            ai=ai,
            workspaces_seen=self.workspaces_seen,
            fatal=self.fatal,
            logger=self.logger,
            registry=reg,
            classifier=self.classifier or DefaultInputClassifier(),
        )
        return engine