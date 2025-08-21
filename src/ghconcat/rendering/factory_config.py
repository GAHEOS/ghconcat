# src/ghconcat/rendering/factory_configs.py
from __future__ import annotations

"""Typed configuration dataclasses for default factories.

These are optional and do not change existing factory call signatures.
They allow clearer DI for advanced callers while preserving test compatibility.
"""

from dataclasses import dataclass
from typing import Optional, Set, Callable
import logging

from ghconcat.io.file_reader_service import FileReadingService
from ghconcat.core.interfaces.walker import WalkerProtocol
from ghconcat.core.interfaces.templating import TemplateEngineProtocol
from ghconcat.core.interfaces.render import RendererProtocol


@dataclass(frozen=True)
class WalkerFactoryConfig:
    """Configuration for building a Walker."""
    header_delim: str
    seen_files: Set[str]
    logger: logging.Logger
    apply_replacements: Callable
    slice_lines: Callable
    clean_lines: Callable
    file_reader_service: FileReadingService


@dataclass(frozen=True)
class RendererFactoryConfig:
    """Configuration for building a Renderer."""
    walker: WalkerProtocol
    template_engine: TemplateEngineProtocol
    header_delim: str
    logger: logging.Logger


@dataclass(frozen=True)
class PathResolverFactoryConfig:
    """Placeholder for potential future options."""
    workspace: Optional[str] = None