"""
rendering.factories – Default DI factories for Walker, Renderer and PathResolver.

These classes are thin facades around existing concrete implementations so
callers can inject them via Protocol-based factories without importing
implementation details at the composition sites.
"""

import logging
from typing import Callable, Optional, Set

from ghconcat.core.interfaces.fs import PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.core.interfaces.factories import (
    WalkerFactoryProtocol,
    RendererFactoryProtocol,
    PathResolverFactoryProtocol,
)
from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.io.walker import WalkerAppender
from ghconcat.rendering.path_resolver import WorkspaceAwarePathResolver
from ghconcat.rendering.renderer import Renderer


class DefaultWalkerFactory(WalkerFactoryProtocol):
    """Default factory for WalkerProtocol.

    By default, it builds a :class:`WalkerAppender` using ghconcat's services.

    Example:
        >>> factory = DefaultWalkerFactory()
        >>> walker = factory(frs, apply_repl, slice_lines, clean_lines, "===== ", set(), logger)
    """

    def __init__(
        self,
        builder: Optional[
            Callable[
                [FileReadingService,
                 Callable[[str, Optional[list[str]], Optional[list[str]]], str],
                 Callable[[list[str], Optional[int], Optional[int], bool], list[str]],
                 Callable[..., list[str]],
                 str,
                 Set[str],
                 logging.Logger],
                WalkerProtocol
            ]
        ] = None
    ) -> None:
        self._builder = builder or self._default_builder

    @staticmethod
    def _default_builder(
        frs: FileReadingService,
        apply_replacements,
        slice_lines,
        clean_lines,
        header_delim: str,
        seen_files: Set[str],
        logger: logging.Logger,
    ) -> WalkerProtocol:
        return WalkerAppender(
            read_file_as_lines=frs.read_lines,
            apply_replacements=apply_replacements,
            slice_lines=slice_lines,
            clean_lines=clean_lines,
            header_delim=header_delim,
            seen_files=seen_files,
            logger=logger,
        )

    def __call__(  # type: ignore[override]
        self,
        file_reader_service: FileReadingService,
        apply_replacements,
        slice_lines,
        clean_lines,
        header_delim: str,
        seen_files: Set[str],
        logger: logging.Logger,
    ) -> WalkerProtocol:
        return self._builder(
            file_reader_service,
            apply_replacements,
            slice_lines,
            clean_lines,
            header_delim,
            seen_files,
            logger,
        )


class DefaultRendererFactory(RendererFactoryProtocol):
    """Default factory for RendererProtocol.

    Example:
        >>> factory = DefaultRendererFactory()
        >>> renderer = factory(walker, template_engine, "===== ", logger)
    """

    def __init__(
        self,
        builder: Optional[
            Callable[[WalkerProtocol, TemplateEngineProtocol, str, logging.Logger], RendererProtocol]
        ] = None
    ) -> None:
        self._builder = builder or self._default_builder

    @staticmethod
    def _default_builder(
        walker: WalkerProtocol,
        template_engine: TemplateEngineProtocol,
        header_delim: str,
        logger: logging.Logger,
    ) -> RendererProtocol:
        return Renderer(
            walker=walker,
            template_engine=template_engine,
            header_delim=header_delim,
            logger=logger,
        )

    def __call__(  # type: ignore[override]
        self,
        walker: WalkerProtocol,
        template_engine: TemplateEngineProtocol,
        header_delim: str,
        logger: logging.Logger,
    ) -> RendererProtocol:
        return self._builder(walker, template_engine, header_delim, logger)


class DefaultPathResolverFactory(PathResolverFactoryProtocol):
    """Default factory for PathResolverProtocol.

    Example:
        >>> factory = DefaultPathResolverFactory()
        >>> resolver = factory()
    """

    def __init__(
        self,
        builder: Optional[Callable[[], PathResolverProtocol]] = None
    ) -> None:
        self._builder = builder or (lambda: WorkspaceAwarePathResolver())

    def __call__(self) -> PathResolverProtocol:  # type: ignore[override]
        return self._builder()