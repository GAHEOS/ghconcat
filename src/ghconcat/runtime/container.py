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
from ghconcat.discovery.url_policy import DefaultUrlAcceptPolicy
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.io.readers import ReaderRegistry, get_global_reader_registry
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.rendering.factory_config import (
    WalkerFactoryConfig,
    RendererFactoryConfig,
    PathResolverFactoryConfig,
)


@dataclass(frozen=True)
class EngineConfig:
    """Immutable configuration blob used to seed the EngineBuilder."""
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

    # Optional factory overrides (kept for API completeness; unused by tests)
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

    # Optional factory configs (opt-in, end-to-end DI convenience)
    walker_cfg: Optional[WalkerFactoryConfig] = None
    renderer_cfg: Optional[RendererFactoryConfig] = None
    path_resolver_cfg: Optional[PathResolverFactoryConfig] = None


@dataclass
class EngineBuilder:
    """Composable builder that wires default factories into an ExecutionEngine."""
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

    # Optional factory overrides / DI hooks
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

    # Optional factory configs (not used by tests, provided for advanced callers)
    walker_cfg: Optional[WalkerFactoryConfig] = None
    renderer_cfg: Optional[RendererFactoryConfig] = None
    path_resolver_cfg: Optional[PathResolverFactoryConfig] = None

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> 'EngineBuilder':
        """Build a new EngineBuilder from a single EngineConfig."""
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
            walker_cfg=cfg.walker_cfg,
            renderer_cfg=cfg.renderer_cfg,
            path_resolver_cfg=cfg.path_resolver_cfg,
        )

    @classmethod
    def from_configs(cls, cfg: EngineConfig, *factory_cfgs) -> 'EngineBuilder':
        """Optional multi-config constructor.

        Accepts EngineConfig and an arbitrary list of factory configs:
        WalkerFactoryConfig, RendererFactoryConfig, PathResolverFactoryConfig.
        This is opt-in and **does not** affect existing behavior/tests.
        """
        builder = cls.from_config(cfg)
        for fc in factory_cfgs:
            if isinstance(fc, WalkerFactoryConfig):
                builder.walker_cfg = fc
            elif isinstance(fc, RendererFactoryConfig):
                builder.renderer_cfg = fc
            elif isinstance(fc, PathResolverFactoryConfig):
                builder.path_resolver_cfg = fc
        return builder

    def _clone_registry_for_run(self) -> ReaderRegistry:
        """Create a suffix-only clone of the global reader registry for a run."""
        g = get_global_reader_registry(self.logger)
        return g.clone_suffix_only()

    def build(self, *, call_openai) -> ExecutionEngine:
        """Materialize an ExecutionEngine with the currently wired factories.

        The method honors an optional attribute `_url_policy_loader` that may
        be set by the CLI layer to inject a custom UrlAcceptPolicy. This keeps
        public signatures intact while enabling `--url-policy module:Class`.
        """
        # Readers & file-service
        reg = self._clone_registry_for_run()
        frs = FileReadingService(registry=reg, logger=self.logger)

        # Factories (resolver/walker/renderer)
        pr_factory = self.path_resolver_factory or DefaultPathResolverFactory()
        w_factory = self.walker_factory or DefaultWalkerFactory()
        r_factory = self.renderer_factory or DefaultRendererFactory()

        # Concrete resolver + walker
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

        # Git manager & URL fetcher factories
        gm_factory = DefaultGitManagerFactory(
            lambda ws: GitRepositoryManager(ws, logger=self.logger, clones_cache=self.clones_cache)
        )

        # Resolve optional custom URL policy set by CLI (if any)
        policy_loader = getattr(self, '_url_policy_loader', None)

        def _policy_instance():
            """Instantiate a UrlAcceptPolicy, falling back to default on errors."""
            try:
                if policy_loader is None:
                    return DefaultUrlAcceptPolicy()
                # If a class/callable is provided, call it; if it's an instance, return it.
                return policy_loader() if callable(policy_loader) else policy_loader
            except Exception as exc:
                self.logger.warning(
                    '⚠  failed to instantiate custom URL policy %r: %s; using default',
                    policy_loader,
                    exc,
                )
                return DefaultUrlAcceptPolicy()

        uf_factory = DefaultUrlFetcherFactory(
            lambda ws: UrlFetcher(
                ws,
                logger=self.logger,
                ssl_ctx_provider=self.ssl_ctx_provider,
                policy=_policy_instance(),
            )
        )

        # Discovery orchestration
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

        # Templating/renderer & AI adapter
        tpl_engine = SingleBraceTemplateEngine(logger=self.logger)
        renderer: RendererProtocol = r_factory(walker, tpl_engine, self.header_delim, self.logger)
        ai = DefaultAIProcessor(call_openai=call_openai, logger=self.logger)

        # Compose final engine
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