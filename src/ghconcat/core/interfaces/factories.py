# src/ghconcat/core/interfaces/factories.py
"""
core.interfaces.factories – Protocols for DI factories (Walker/Renderer/PathResolver).

These protocols standardize the dependency-injection surface so higher-level
composition (e.g., EngineBuilder) can accept pluggable factories without
depending on concrete implementations.
"""

import logging
from typing import Callable, Optional, Protocol, Set, runtime_checkable

from ghconcat.core.interfaces.fs import PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.core.interfaces.walker import WalkerProtocol


@runtime_checkable
class WalkerFactoryProtocol(Protocol):
    """Factory that builds a WalkerProtocol using ghconcat's low-level services."""

    def __call__(
        self,
        file_reader_service: "ghconcat.io.file_reader_service.FileReadingService",
        apply_replacements: Callable[[str, Optional[list[str]], Optional[list[str]]], str],
        slice_lines: Callable[[list[str], Optional[int], Optional[int], bool], list[str]],
        clean_lines: Callable[..., list[str]],
        header_delim: str,
        seen_files: Set[str],
        logger: logging.Logger,
    ) -> WalkerProtocol:  # pragma: no cover - interface
        ...


@runtime_checkable
class RendererFactoryProtocol(Protocol):
    """Factory that builds a RendererProtocol from a Walker and a template engine."""

    def __call__(
        self,
        walker: WalkerProtocol,
        template_engine: TemplateEngineProtocol,
        header_delim: str,
        logger: logging.Logger,
    ) -> RendererProtocol:  # pragma: no cover - interface
        ...


@runtime_checkable
class PathResolverFactoryProtocol(Protocol):
    """Factory that creates a PathResolverProtocol instance."""

    def __call__(self) -> PathResolverProtocol:  # pragma: no cover - interface
        ...