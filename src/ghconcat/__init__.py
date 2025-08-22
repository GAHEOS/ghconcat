from __future__ import annotations

import logging
from typing import Optional

from ghconcat.constants import HEADER_DELIM
from ghconcat.cli import GhConcat
from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.runtime.policies import DefaultPolicies
from ghconcat.runtime.runner import EngineRunner
from ghconcat.parsing.parser import _build_parser
from ghconcat.runtime.sdk import _call_openai, _perform_upgrade
from ghconcat.rendering.template_engine import SingleBraceTemplateEngine
from ghconcat.rendering.path_resolver import (
    DefaultPathResolver,
    PathResolverProtocol,
    WorkspaceAwarePathResolver,
)
from ghconcat.rendering.renderer import Renderer, RendererProtocol
from ghconcat.rendering.execution import ExecutionEngine
from ghconcat.logging.helpers import get_logger
from ghconcat.core.interfaces.templating import TemplateEngineProtocol

__version__ = '0.9.2'


def renderer_factory(
    *,
    walker,
    template_engine: Optional[TemplateEngineProtocol] = None,
    header_delim: str = HEADER_DELIM,
    logger: Optional[logging.Logger] = None,
) -> Renderer:
    """Factory helper that returns a concrete Renderer.

    Falls back to SingleBraceTemplateEngine when no TemplateEngine is provided.
    """
    engine = template_engine or SingleBraceTemplateEngine(logger=logger)
    lg = logger or get_logger('render')
    return Renderer(walker=walker, template_engine=engine, header_delim=header_delim, logger=lg)


def path_resolver_factory(*, workspace: Optional[str] = None) -> WorkspaceAwarePathResolver:
    """Factory helper that returns a WorkspaceAwarePathResolver."""
    from pathlib import Path as _P

    ws = _P(workspace) if workspace else None
    return WorkspaceAwarePathResolver(workspace=ws)


__all__ = [
    'GhConcat',
    'HEADER_DELIM',
    'renderer_factory',
    'path_resolver_factory',
    'EngineBuilder',
    'EngineConfig',
    'DefaultPolicies',
    'EngineRunner',
    '_call_openai',
    '_perform_upgrade',
    '_build_parser',
    'ExecutionEngine',
    'DefaultPathResolver',
    'WorkspaceAwarePathResolver',
    'SingleBraceTemplateEngine',
]