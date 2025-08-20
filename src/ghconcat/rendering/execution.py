import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ghconcat.parsing.directives import DirNode
from ghconcat.parsing.list_ops import split_list
from ghconcat.core.interfaces.fs import FileDiscoveryProtocol, PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.io.readers import ReaderRegistry, get_global_reader_registry
from ghconcat.io.reader_context import ReaderMappingScope
from ghconcat.io.html_reader import HtmlToTextReader
from ghconcat.utils.paths import looks_like_url, looks_like_git_spec


def _reclassify_add_exclude(ns: argparse.Namespace) -> None:
    """Reclassify tokens in add/exclude lists into local/git/url/scrape buckets.

    This function is kept as-is to preserve behavior and test compatibility.
    """
    depth = getattr(ns, 'url_depth', 0) or 0
    add_local = list(getattr(ns, 'add_path', []) or [])
    exc_local = list(getattr(ns, 'exclude_path', []) or [])

    new_add_local: list[str] = []
    new_exc_local: list[str] = []
    new_urls: list[str] = []
    new_url_scrape: list[str] = []
    new_git_inc: list[str] = []
    new_git_exc: list[str] = []

    for tok in add_local:
        if looks_like_git_spec(tok):
            new_git_inc.append(tok)
        elif looks_like_url(tok):
            (new_url_scrape if depth > 0 else new_urls).append(tok)
        else:
            new_add_local.append(tok)

    for tok in exc_local:
        if looks_like_git_spec(tok):
            new_git_exc.append(tok)
        elif looks_like_url(tok):
            new_urls = [u for u in new_urls if u != tok]
            new_url_scrape = [u for u in new_url_scrape if u != tok]
        else:
            new_exc_local.append(tok)

    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq).keys())

    ns.add_path = _dedup(new_add_local)
    ns.exclude_path = _dedup(new_exc_local)
    ns.urls = _dedup(new_urls)
    ns.url_scrape = _dedup(new_url_scrape)
    ns.git_path = _dedup(new_git_inc)
    ns.git_exclude = _dedup(new_git_exc)


class ExecutionEngine:
    """Coordinates parsing, discovery, rendering and optional AI post-processing."""

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser],
        post_parse: Callable[[argparse.Namespace], None],
        merge_ns: Callable[[argparse.Namespace, argparse.Namespace], argparse.Namespace],
        expand_tokens: Callable[[List[str], Dict[str, str]], List[str]],
        parse_env_items: Callable[[Optional[List[str]]], Dict[str, str]],
        resolver: PathResolverProtocol,
        discovery: FileDiscoveryProtocol,
        renderer: RendererProtocol,
        ai: AIProcessorProtocol,
        workspaces_seen: set[Path],
        fatal: Callable[[str], None],
        logger: Optional[logging.Logger] = None,
        registry: Optional[ReaderRegistry] = None,
        registry_factory: Optional[Callable[[], ReaderRegistry]] = None,
    ) -> None:
        """Initialize the execution engine.

        Args:
            parser_factory: Factory for the argparse parser.
            post_parse: Function to normalize/transform the parsed namespace.
            merge_ns: Function to merge parent and child namespaces.
            expand_tokens: Token expansion (env vars and --none handling).
            parse_env_items: Parser for -e/-E items into dict.
            resolver: Path resolver for workdir/workspace/template/output.
            discovery: FileDiscovery implementation (local/git/url/scrape).
            renderer: Renderer implementation.
            ai: AIProcessor implementation.
            workspaces_seen: Set of observed workspaces to support cache purge.
            fatal: Callback to terminate with an error message.
            logger: Optional logger.
            registry: Optional ReaderRegistry (used directly if provided).
            registry_factory: Optional factory to build a registry if not given.
        """
        self._parser_factory = parser_factory
        self._post_parse = post_parse
        self._merge_ns = merge_ns
        self._expand_tokens = expand_tokens
        self._parse_env_items = parse_env_items
        self._resolver = resolver
        self._discovery = discovery
        self._renderer = renderer
        self._ai = ai
        self._workspaces_seen = workspaces_seen
        self._fatal = fatal
        self._log = logger or logging.getLogger('ghconcat.exec')

        if registry is not None:
            self._registry = registry
        elif registry_factory is not None:
            self._registry = registry_factory()
        else:
            # Clone suffix-only to allow per-run temporary overrides safely.
            self._registry = get_global_reader_registry(self._log).clone_suffix_only()

        self._read_file_as_lines = lambda fp: self._registry.read_lines(fp)
        self._strict_ws = os.getenv('GHCONCAT_STRICT_WS') == '1'

    def execute_node(
        self,
        node: DirNode,
        ns_parent: Optional[argparse.Namespace],
        *,
        level: int = 0,
        parent_root: Optional[Path] = None,
        parent_workspace: Optional[Path] = None,
        inherited_vars: Optional[Dict[str, str]] = None,
        gh_dump: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, str], str]:
        """Execute a directive node and return the resulting variables and text.

        This method preserves all existing behaviors and CLI semantics
        expected by the current test suite.
        """
        inherited_vars = inherited_vars or {}

        # 1) Parse current node tokens (env expansion + --none stripping)
        tokens = self._expand_tokens(node.tokens, inherited_env=inherited_vars)
        ns_self = self._parser_factory().parse_args(tokens)
        self._post_parse(ns_self)
        ns_effective = self._merge_ns(ns_parent, ns_self) if ns_parent else ns_self

        # Root node holds the global dump accumulator
        if level == 0:
            gh_dump = []

        # 2) Resolve workdir/root and workspace with proper inheritance
        if ns_parent is None:
            base_for_root = Path.cwd()
            root = self._resolver.resolve(base_for_root, ns_effective.workdir or '.')
        elif ns_self.workdir not in (None, ''):
            base_for_root = parent_root or Path.cwd()
            root = self._resolver.resolve(base_for_root, ns_self.workdir)
        else:
            root = parent_root or Path.cwd()

        if ns_parent is None:
            if ns_self.workspace not in (None, ''):
                workspace = self._resolver.resolve(root, ns_self.workspace)
            else:
                workspace = root
        elif ns_self.workspace not in (None, ''):
            base_ws = parent_workspace or root
            workspace = self._resolver.resolve(base_ws, ns_self.workspace)
        else:
            workspace = parent_workspace or root

        # Optionally propagate workspace to resolver
        try:
            setter = getattr(self._resolver, 'set_workspace_root', None)
            if callable(setter):
                setter(workspace)
        except Exception:
            pass

        def _guard_ws(path: Path) -> Path:
            """Validate that a path is within workspace when strict mode is on."""
            if self._strict_ws and (not self._resolver.is_within_workspace(path)):
                self._fatal(f'unsafe path outside workspace: {path}')
                raise SystemExit(1)
            return path

        self._workspaces_seen.add(workspace)
        ns_effective.workspace = str(workspace)

        if not root.exists():
            self._fatal(f'--workdir {root} not found')
            raise SystemExit(1)
        if not workspace.exists():
            self._fatal(f'--workspace {workspace} not found')
            raise SystemExit(1)

        # Optional HTML → text mapping scope
        maybe_scope = None
        if getattr(ns_effective, 'strip_html', False):
            scope = ReaderMappingScope(self._registry)
            scope.__enter__()
            scope.register(['.html', '.htm', '.xhtml'], HtmlToTextReader(logger=self._log))
            maybe_scope = scope

        try:
            dump_raw = ''

            # 3) Discovery: classify add/exclude into local/git/url/scrape
            _reclassify_add_exclude(ns_effective)

            if ns_effective.add_path or ns_effective.git_path or ns_effective.urls or ns_effective.url_scrape:
                suffixes = split_list(getattr(ns_effective, 'suffix', None))
                exclude_suf = split_list(getattr(ns_effective, 'exclude_suf', None))

                local_files = self._discovery.gather_local(
                    add_paths=ns_effective.add_path,
                    exclude_paths=ns_effective.exclude_path,
                    suffixes=suffixes,
                    exclude_suf=exclude_suf,
                    root=root,
                )
                git_files = self._discovery.collect_git(
                    git_specs=ns_effective.git_path,
                    git_exclude=ns_effective.git_exclude,
                    workspace=workspace,
                    suffixes=suffixes,
                    exclude_suf=exclude_suf,
                )
                remote_files = self._discovery.fetch_urls(urls=ns_effective.urls, workspace=workspace)
                scraped_files = self._discovery.scrape_urls(
                    seeds=ns_effective.url_scrape,
                    workspace=workspace,
                    suffixes=suffixes,
                    exclude_suf=exclude_suf,
                    max_depth=getattr(ns_effective, 'url_depth', 0) or 0,
                    same_host_only=not getattr(ns_effective, 'url_cross_domain', False),
                )

                files = [*local_files, *remote_files, *scraped_files, *git_files]
                if files:
                    dump_raw = self._renderer.concat(files, ns_effective, header_root=root)
        finally:
            if maybe_scope is not None:
                maybe_scope.__exit__(None, None, None)

        # 4) Build variable maps (global/local)
        ctx_name = node.name
        global_env_map = self._parse_env_items(getattr(ns_effective, 'global_env', None))
        local_env_map = self._parse_env_items(getattr(ns_effective, 'env_vars', None))

        inherited_for_children = {**(inherited_vars or {}), **global_env_map}
        vars_local = {**inherited_for_children, **local_env_map}

        if ctx_name:
            vars_local[f'_r_{ctx_name}'] = dump_raw
            vars_local[ctx_name] = dump_raw

        if gh_dump is not None:
            gh_dump.append(dump_raw)

        # 5) Execute children
        for child in node.children:
            child_vars, _ = self.execute_node(
                child,
                ns_effective,
                level=level + 1,
                parent_root=root,
                parent_workspace=workspace,
                inherited_vars=inherited_for_children,
                gh_dump=gh_dump,
            )
            vars_local.update(child_vars)
            inherited_for_children.update(child_vars)
            nxt = child_vars.get('__GH_NEXT_CHILD_TEMPLATE__', None)
            if nxt is not None:
                ns_effective.child_template = nxt or None

        # 6) Templating
        rendered = dump_raw
        parent_child_tpl = getattr(ns_parent, 'child_template', None) if ns_parent else None
        chosen_tpl = getattr(ns_effective, 'template', None) or parent_child_tpl

        if chosen_tpl:
            tpl_path = self._resolver.resolve(workspace, chosen_tpl)
            tpl_path = _guard_ws(tpl_path)
            if not tpl_path.exists():
                self._fatal(f'template {tpl_path} not found')
                raise SystemExit(1)
            rendered = self._renderer.render_template(tpl_path, vars_local, ''.join(gh_dump or []))

        if ctx_name:
            vars_local[f'_t_{ctx_name}'] = rendered
            vars_local[ctx_name] = rendered

        # 7) Output & AI
        final_out = rendered
        out_path: Optional[Path] = None

        # ✅ FIX: robust, type-safe handling of -o/--output (and 'none' sentinel)
        out_val = getattr(ns_effective, 'output', None)
        if out_val not in (None, '') and str(out_val).lower() != 'none':
            out_path = self._resolver.resolve(workspace, out_val)
            out_path = _guard_ws(out_path)

        # AI branch writes to file (explicit -o or temp file)
        if getattr(ns_effective, 'ai', False):
            if out_path is None:
                tf = tempfile.NamedTemporaryFile(delete=False, dir=workspace, suffix='.ai.txt')
                tf.close()
                out_path = Path(tf.name)

            sys_prompt = ''
            ai_sys = getattr(ns_effective, 'ai_system_prompt', None)
            if ai_sys and str(ai_sys).lower() != 'none':
                spath = self._resolver.resolve(workspace, ai_sys)
                spath = _guard_ws(spath)
                if not spath.exists():
                    self._fatal(f'system prompt {spath} not found')
                    raise SystemExit(1)
                sys_prompt = self._renderer.interpolate(spath.read_text(encoding='utf-8'), vars_local)

            seeds_path = None
            ai_seeds = getattr(ns_effective, 'ai_seeds', None)
            if ai_seeds and str(ai_seeds).lower() != 'none':
                seeds_path = self._resolver.resolve(workspace, ai_seeds)
                seeds_path = _guard_ws(seeds_path)

            self._ai.run(
                prompt=rendered,
                out_path=out_path,
                model=getattr(ns_effective, 'ai_model', ''),
                system_prompt=sys_prompt,
                temperature=getattr(ns_effective, 'ai_temperature', None),
                top_p=getattr(ns_effective, 'ai_top_p', None),
                presence_penalty=getattr(ns_effective, 'ai_presence_penalty', None),
                frequency_penalty=getattr(ns_effective, 'ai_frequency_penalty', None),
                seeds_path=seeds_path,
                max_tokens=getattr(ns_effective, 'ai_max_tokens', None),
                reasoning_effort=getattr(ns_effective, 'ai_reasoning_effort', None),
            )
            final_out = out_path.read_text(encoding='utf-8')

        if ctx_name:
            vars_local[f'_ia_{ctx_name}'] = final_out
            vars_local[ctx_name] = final_out

        # Non-AI: write output only if -o/--output was set
        if out_path and (not getattr(ns_effective, 'ai', False)):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(final_out, encoding='utf-8')
            self._log.info('✔ Output written → %s', out_path)

        # 8) Stdout behavior
        force_stdout = bool(getattr(ns_effective, 'to_stdout', False))
        auto_root_stdout = (level == 0) and (getattr(ns_effective, 'output', None) in (None, 'none'))

        if force_stdout or (auto_root_stdout and (not force_stdout)):
            if not sys.stdout.isatty():
                sys.stdout.write(final_out)
            else:
                print(final_out, end='')

        # Root-level: if final_out is empty but we accumulated gh_dump, use it
        if level == 0 and final_out == '' and gh_dump:
            final_out = ''.join(gh_dump)

        if level == 0 and gh_dump is not None:
            vars_local['ghconcat_dump'] = ''.join(gh_dump)

        # Pass child template selection up the chain
        vars_local['__GH_NEXT_CHILD_TEMPLATE__'] = getattr(ns_effective, 'child_template', None) or ''
        return (vars_local, final_out)