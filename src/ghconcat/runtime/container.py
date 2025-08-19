# src/ghconcat/runtime/container.py
"""
runtime.container – Dependency Injection composition for ghconcat.

This module exposes EngineBuilder, a thin composition helper that wires all
runtime collaborators required by ExecutionEngine while keeping public CLI
symbols untouched (full test-suite compatibility).

Design goals
------------
• Zero behavior drift: same wiring as the legacy cli._execute_node().
• Explicit DI: readable seams for tests and future adapters.
• One-run ReaderRegistry clone to support temporary reader mappings
  (e.g., -K/--textify-html) consistently across the pipeline.
• NEW: Optional factories to inject Walker/Renderer/PathResolver,
  enabling high-level tests to provide doubles without touching internals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Set, Tuple

from ghconcat.io.readers import ReaderRegistry, get_global_reader_registry
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.io.walker import WalkerAppender
from ghconcat.rendering.path_resolver import (
    DefaultPathResolver,
    WorkspaceAwarePathResolver,
)
from ghconcat.rendering.renderer import Renderer
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.discovery.file_discovery import FileDiscovery
from ghconcat.discovery.git_repository import GitRepositoryManager
from ghconcat.discovery.url_fetcher import UrlFetcher
from ghconcat.core import DefaultGitManagerFactory, DefaultUrlFetcherFactory
from ghconcat.core.interfaces.fs import FileDiscoveryProtocol, PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.ai.ai_processor import DefaultAIProcessor
from ghconcat.rendering.execution import ExecutionEngine

# NEW: DI factory protocols
from ghconcat.core.interfaces.factories import (
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
)


@dataclass
class EngineBuilder:
    """Build a fully-wired ExecutionEngine instance.

    Parameters
    ----------
    logger:
        Logger instance to propagate to every component.
    header_delim:
        Banner delimiter injected into Walker/Renderer.
    seen_files:
        Shared de-duplication set for headers (same lifetime as a GhConcat.run()).
    clones_cache:
        Shared in-memory cache for git shallow-clone destinations.
    workspaces_seen:
        Shared set of workspaces to purge caches at the end.
    ssl_ctx_provider:
        Callable(url) -> ssl.SSLContext | None used by UrlFetcher.
    parser_factory/post_parse/merge_ns/expand_tokens/parse_env_items:
        Strategy callables taken from the CLI layer to preserve semantics.
    interpolate:
        String interpolation function (legacy single-brace) kept for builder
        compatibility; the Renderer now receives a TemplateEngine directly.
    apply_replacements/slice_lines/clean_lines:
        Text ops coming from services already standardized in ghconcat.
    fatal:
        Fatal handler to abort (CLI-compatible).

    Factories (optional)
    --------------------
    walker_factory:
        Protocol-based factory that builds the Walker.
    renderer_factory:
        Protocol-based factory that builds the Renderer.
    discovery_factory:
        Callable(walker, git_factory, url_factory, resolver, logger) -> FileDiscoveryProtocol
    path_resolver_factory:
        Protocol-based factory that builds the PathResolver.
    """

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
    clean_lines: Callable[
        [list[str], str],
        list[str]
    ] | Callable[
        [list[str], str, bool, bool, bool, bool, bool],
        list[str]
    ]
    fatal: Callable[[str], None]

    # Updated to Protocol-based optional factories
    walker_factory: Optional[WalkerFactoryProtocol] = None
    renderer_factory: Optional[RendererFactoryProtocol] = None
    discovery_factory: Optional[
        Callable[
            [WalkerProtocol,
             DefaultGitManagerFactory,
             DefaultUrlFetcherFactory,
             PathResolverProtocol,
             logging.Logger],
            FileDiscoveryProtocol
        ]
    ] = None
    path_resolver_factory: Optional[PathResolverFactoryProtocol] = None

    def _clone_registry_for_run(self) -> ReaderRegistry:
        """Return a shallowly-cloned ReaderRegistry from the global singleton."""
        g = get_global_reader_registry(self.logger)
        cloned = ReaderRegistry(default_reader=g.default_reader)
        for rule in getattr(g, "_rules", []):
            if getattr(rule, "predicate", None) is None and getattr(rule, "suffixes", None):
                cloned.register(list(rule.suffixes), rule.reader)  # type: ignore[attr-defined]
        cloned.set_default(g.default_reader)
        return cloned

    def build(self, *, call_openai) -> ExecutionEngine:
        """Compose and return a ready-to-use ExecutionEngine."""
        reg = self._clone_registry_for_run()
        frs = FileReadingService(registry=reg, logger=self.logger)

        resolver: PathResolverProtocol
        if self.path_resolver_factory is not None:
            resolver = self.path_resolver_factory()
        else:
            resolver = WorkspaceAwarePathResolver()

        if self.walker_factory is not None:
            walker: WalkerProtocol = self.walker_factory(
                frs,
                self.apply_replacements,
                self.slice_lines,
                self.clean_lines,  # type: ignore[arg-type]
                self.header_delim,
                self.seen_files,
                self.logger,
            )
        else:
            walker = WalkerAppender(
                read_file_as_lines=frs.read_lines,
                apply_replacements=self.apply_replacements,
                slice_lines=self.slice_lines,
                clean_lines=self.clean_lines,  # type: ignore[arg-type]
                header_delim=self.header_delim,
                seen_files=self.seen_files,
                logger=self.logger,
            )

        gm_factory = DefaultGitManagerFactory(
            lambda ws: GitRepositoryManager(ws, logger=self.logger, clones_cache=self.clones_cache)
        )
        uf_factory = DefaultUrlFetcherFactory(
            lambda ws: UrlFetcher(ws, logger=self.logger, ssl_ctx_provider=self.ssl_ctx_provider)
        )

        if self.discovery_factory is not None:
            discovery: FileDiscoveryProtocol = self.discovery_factory(
                walker, gm_factory, uf_factory, resolver, self.logger
            )
        else:
            discovery = FileDiscovery(
                walker=walker,
                git_manager_factory=gm_factory,
                url_fetcher_factory=uf_factory,
                resolver=resolver,
                logger=self.logger,
            )

        tpl_engine: TemplateEngineProtocol = SingleBraceTemplateEngine(logger=self.logger)

        if self.renderer_factory is not None:
            renderer: RendererProtocol = self.renderer_factory(
                walker, tpl_engine, self.header_delim, self.logger
            )
        else:
            renderer = Renderer(
                walker=walker,
                template_engine=tpl_engine,
                header_delim=self.header_delim,
                logger=self.logger,
            )

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
        )
        return engine