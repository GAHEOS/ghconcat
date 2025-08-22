from __future__ import annotations

from typing import Any, Callable, Optional
from pathlib import Path

from ghconcat.runtime.container import EngineBuilder, EngineConfig
from ghconcat.runtime.helpers import (
    TextReplacer,
    EnvExpander,
    NamespaceMerger,
    make_line_ops,
    get_ssl_ctx_provider,
)
from ghconcat.parsing.parser import _build_parser


def build_engine_config(
    *,
    logger: Any,
    header_delim: str,
    seen_files: set[Path] | set[str],
    clones_cache: dict[tuple[str, str | None], Path],
    workspaces_seen: set[Path],
    fatal_handler: Callable[[str], None],
) -> EngineConfig:
    """Crea una EngineConfig completa con todos los fallbacks perezosos."""
    replacer = TextReplacer(logger=logger)
    envx = EnvExpander(logger=logger)
    merger = NamespaceMerger(logger=logger)
    line_ops = make_line_ops(logger)

    return EngineConfig(
        logger=logger,
        header_delim=header_delim,
        seen_files=seen_files,
        clones_cache=clones_cache,
        workspaces_seen=workspaces_seen,
        ssl_ctx_provider=get_ssl_ctx_provider,
        parser_factory=_build_parser,
        post_parse=merger.post_parse,
        merge_ns=merger.merge,
        expand_tokens=envx.expand_tokens,
        parse_env_items=envx.parse_items,
        apply_replacements=replacer.apply,
        slice_lines=line_ops.slice_lines,
        clean_lines=line_ops.clean_lines,
        fatal=fatal_handler,
        classifier=None,
    )


def build_engine(
    cfg: EngineConfig,
    *,
    call_openai,
    url_policy_cls: Optional[type] = None,
):
    """Construye el engine desde una EngineConfig y aplica el policy loader opcional."""
    builder = EngineBuilder.from_config(cfg)
    if url_policy_cls is not None:
        # Respeta el mecanismo actual del builder para inyectar la URL policy.
        setattr(builder, "_url_policy_loader", url_policy_cls)
    engine = builder.build(call_openai=call_openai)
    return engine