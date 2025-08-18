"""
execution – ExecutionEngine for ghconcat directive trees.

This module encapsulates the previous `_execute_node` flow from the
monolithic implementation into a reusable, dependency-injected class.

Design goals
------------
• Keep 1:1 external behavior with the legacy `_execute_node`.
• Accept pluggable collaborators for path resolution, discovery, rendering,
  and AI invocation so the engine can be used as a library component.
• Remain free of CLI I/O side-effects beyond what the original flow did
  (stdout emission is preserved as per flags).

Public API
----------
ExecutionEngine.execute(node, ns_parent, **opts) -> (vars_map, final_text)
"""

import argparse
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Callable
import logging

from .envctx import EnvContext
from .flags import VALUE_FLAGS as _VALUE_FLAGS
from .walker import WalkerAppender


HEADER_DELIM: str = "===== "
TOK_NONE: str = "none"


class PathResolver:
    """Simple path utility with injectable strategy (test-friendly)."""

    def resolve(self, base: Path, maybe: Optional[str]) -> Path:
        """Resolve *maybe* against *base* unless it is already absolute."""
        if maybe is None:
            return base
        pth = Path(maybe).expanduser()
        return pth if pth.is_absolute() else (base / pth).resolve()


class FileDiscovery:
    """Abstraction over local/remote/git file collection.

    The default implementation wires WalkerAppender + UrlFetcher + GitRepositoryManager
    via callables passed in the constructor.
    """

    def __init__(
        self,
        *,
        gather_files: Callable[[List[Path], List[Path], List[str], List[str]], List[Path]],
        collect_git_files: Callable[
            [List[str] | None, List[str] | None, Path, List[str], List[str]],
            List[Path],
        ],
        fetch_urls: Callable[[List[str], Path], List[Path]],
        scrape_urls: Callable[
            [List[str], Path],
            List[Path],
        ] | None = None,
        scrape_urls_ext: Callable[
            [List[str], Path, List[str], List[str], int, bool], List[Path]
        ] | None = None,
    ) -> None:
        """Create a FileDiscovery façade.

        Either `scrape_urls` (old simple signature) or `scrape_urls_ext`
        (full signature) can be provided; the latter takes precedence.
        """
        self._gather_files = gather_files
        self._collect_git_files = collect_git_files
        self._fetch_urls = fetch_urls
        self._scrape_urls = scrape_urls
        self._scrape_urls_ext = scrape_urls_ext

    def gather_local(
        self,
        add_path: List[Path],
        exclude_dirs: List[Path],
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        return self._gather_files(add_path, exclude_dirs, suffixes, exclude_suf)

    def collect_git(
        self,
        git_specs: List[str] | None,
        git_exclude_specs: List[str] | None,
        workspace: Path,
        suffixes: List[str],
        exclude_suf: List[str],
    ) -> List[Path]:
        return self._collect_git_files(git_specs, git_exclude_specs, workspace, suffixes, exclude_suf)

    def fetch(self, urls: List[str], cache_root: Path) -> List[Path]:
        return self._fetch_urls(urls, cache_root)

    def scrape(
        self,
        seeds: List[str],
        cache_root: Path,
        *,
        suffixes: List[str],
        exclude_suf: List[str],
        max_depth: int,
        same_host_only: bool,
    ) -> List[Path]:
        if self._scrape_urls_ext is not None:
            return self._scrape_urls_ext(seeds, cache_root, suffixes, exclude_suf, max_depth, same_host_only)
        if self._scrape_urls is not None:
            # Legacy compatibility path (kept for safety)
            return self._scrape_urls(seeds, cache_root)
        return []


class Renderer:
    """Rendering façade: template interpolation + optional wrap."""

    def __init__(
        self,
        *,
        interpolate: Callable[[str, Dict[str, str]], str],
        header_delim: str = HEADER_DELIM,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._interpolate = interpolate
        self._header_delim = header_delim
        self._log = logger or logging.getLogger("ghconcat.exec.renderer")

    def render_template(self, template_text: str, mapping: Dict[str, str]) -> str:
        """Apply interpolation with ghconcat's `{var}` / `{{var}}` rules."""
        return self._interpolate(template_text, mapping)

    @property
    def header_delim(self) -> str:
        return self._header_delim


class AIProcessor:
    """Thin façade around the AI call, injected for testability."""

    def __init__(
        self,
        *,
        call_openai: Callable[..., None],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._call = call_openai
        self._log = logger or logging.getLogger("ghconcat.exec.ai")

    def run(
        self,
        prompt: str,
        out_path: Path,
        *,
        model: str,
        system_prompt: str,
        temperature: float | None,
        top_p: float | None,
        presence_pen: float | None,
        freq_pen: float | None,
        seeds_path: Optional[Path],
        timeout: int = 1800,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> None:
        """Delegate to the injected OpenAI caller."""
        self._call(
            prompt,
            out_path,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            presence_pen=presence_pen,
            freq_pen=freq_pen,
            seeds_path=seeds_path,
            timeout=timeout,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )


class ExecutionEngine:
    """High-level executor for a directive tree (DirNode).

    This class mirrors the legacy `_execute_node` logic while depending on
    injectable collaborators. It is intentionally state-light; cross-context
    state such as seen headers is still handled by WalkerAppender via the
    injected `seen_files` set.

    Parameters
    ----------
    parser_factory:
        Callable that returns the `argparse.ArgumentParser` configured for a
        single context. It must match ghconcat's `_build_parser()` behavior.
    post_parse:
        Callable to normalize argparse namespaces (tri-state flags resolution).
    env_context:
        Instance of `EnvContext` to perform env expansion on tokens.
    path_resolver:
        Strategy for resolving workdir/workspace/template/output paths.
    file_discovery:
        `FileDiscovery` wrapper exposing local/git/url/scrape methods.
    renderer:
        `Renderer` implementing template interpolation and header constants.
    ai_processor:
        `AIProcessor` for optional AI post-processing.
    walker_factory:
        Callable that returns a properly wired WalkerAppender instance.
    logger:
        Optional logger for consistent messaging.
    """

    def __init__(
        self,
        *,
        parser_factory: Callable[[], argparse.ArgumentParser],
        post_parse: Callable[[argparse.Namespace], None],
        env_context: EnvContext,
        path_resolver: PathResolver,
        file_discovery: FileDiscovery,
        renderer: Renderer,
        ai_processor: AIProcessor,
        walker_factory: Callable[[Set[str]], WalkerAppender],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._mk_parser = parser_factory
        self._post_parse = post_parse
        self._env = env_context
        self._paths = path_resolver
        self._fs = file_discovery
        self._rend = renderer
        self._ai = ai_processor
        self._walker_factory = walker_factory
        self._log = logger or logging.getLogger("ghconcat.exec")

        self._seen_files: Set[str] = set()
        self._workspaces_seen: Set[Path] = set()

    # ---- Public API -----------------------------------------------------

    def execute(
        self,
        node,
        ns_parent: Optional[argparse.Namespace],
        *,
        level: int = 0,
        parent_root: Optional[Path] = None,
        parent_workspace: Optional[Path] = None,
        inherited_vars: Optional[Dict[str, str]] = None,
        gh_dump: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, str], str]:
        """Execute one DirNode and its children (returns vars, final_output)."""
        inherited_vars = inherited_vars or {}
        tokens = self._env.expand_tokens(node.tokens, inherited_vars, value_flags=_VALUE_FLAGS, none_value="none")

        ns_self = self._mk_parser().parse_args(tokens)
        self._post_parse(ns_self)
        ns_effective = self._merge_ns(ns_parent, ns_self)

        if level == 0:
            gh_dump = []
            self._seen_files.clear()

        # Workdir/workspace resolution (identical semantics to legacy)
        if ns_parent is None:
            base_for_root = Path.cwd()
            root = self._paths.resolve(base_for_root, ns_effective.workdir or ".")
        else:
            if ns_self.workdir not in (None, ""):
                base_for_root = parent_root or Path.cwd()
                root = self._paths.resolve(base_for_root, ns_self.workdir)
            else:
                root = parent_root or Path.cwd()

        if ns_parent is None:
            if ns_self.workspace not in (None, ""):
                workspace = self._paths.resolve(root, ns_self.workspace)
            else:
                workspace = root
        else:
            if ns_self.workspace not in (None, ""):
                base_ws = parent_workspace or root
                workspace = self._paths.resolve(base_ws, ns_self.workspace)
            else:
                workspace = parent_workspace or root

        self._workspaces_seen.add(workspace)
        ns_effective.workspace = str(workspace)

        if not root.exists():
            self._fatal(f"--workdir {root} not found")
        if not workspace.exists():
            self._fatal(f"--workspace {workspace} not found")

        # Env vars (local/global)
        global_env_map = self._env.parse_items(ns_effective.global_env, on_error=lambda m: self._fatal(m))
        local_env_map = self._env.parse_items(ns_effective.env_vars, on_error=lambda m: self._fatal(m))

        inherited_for_children = {**inherited_vars, **global_env_map}
        vars_local = {**inherited_for_children, **local_env_map}
        ctx_name = getattr(node, "name", None)

        parent_child_tpl = getattr(ns_parent, "child_template", None) if ns_parent else None
        local_child_tpl = getattr(ns_self, "child_template", None)
        child_tpl_for_descendants = local_child_tpl if local_child_tpl not in (None, "") else parent_child_tpl
        ns_effective.child_template = child_tpl_for_descendants

        # Discovery + concatenation
        dump_raw = ""
        if (
            ns_effective.add_path
            or ns_effective.git_path
            or ns_effective.urls
            or ns_effective.url_scrape
        ):
            suffixes = self._split_list(ns_effective.suffix)
            exclude_suf = self._split_list(ns_effective.exclude_suf)

            local_files: List[Path] = []
            if ns_effective.add_path:
                local_files = self._fs.gather_local(
                    add_path=[
                        Path(p) if Path(p).is_absolute() else (root / p).resolve()
                        for p in ns_effective.add_path
                    ],
                    exclude_dirs=[
                        Path(p) if Path(p).is_absolute() else (root / p).resolve()
                        for p in ns_effective.exclude_path or []
                    ],
                    suffixes=suffixes,
                    exclude_suf=exclude_suf,
                )

            git_files: List[Path] = self._fs.collect_git(
                ns_effective.git_path,
                ns_effective.git_exclude,
                workspace,
                suffixes,
                exclude_suf,
            )

            remote_files: List[Path] = []
            if ns_effective.urls:
                remote_files = self._fs.fetch(ns_effective.urls, workspace)

            scraped_files: List[Path] = []
            if ns_effective.url_scrape:
                max_depth = 2 if ns_effective.url_scrape_depth is None else ns_effective.url_scrape_depth
                scraped_files = self._fs.scrape(
                    ns_effective.url_scrape,
                    workspace,
                    suffixes=suffixes,
                    exclude_suf=exclude_suf,
                    max_depth=max_depth,
                    same_host_only=not ns_effective.disable_url_domain_only,
                )

            files = [*local_files, *remote_files, *scraped_files, *git_files]

            if files:
                wrapped: Optional[List[Tuple[str, str]]] = [] if ns_effective.wrap_lang else None
                wa = self._walker_factory(self._seen_files)
                dump_raw = wa.concat_files(files, ns_effective, header_root=root, wrapped=wrapped)

                if ns_effective.wrap_lang and wrapped:
                    fenced: List[str] = []
                    for hp, body in wrapped:
                        hdr = "" if ns_effective.skip_headers else f"{self._rend.header_delim}{hp} {self._rend.header_delim}\n"
                        fenced.append(
                            f"{hdr}```{ns_effective.wrap_lang or Path(hp).suffix.lstrip('.')}\n"
                            f"{body}\n```\n"
                        )
                    dump_raw = "".join(fenced)

        # Context variables exposure
        if ctx_name:
            vars_local[f"_r_{ctx_name}"] = dump_raw
            vars_local[ctx_name] = dump_raw
        if gh_dump is not None:
            gh_dump.append(dump_raw)

        self._env.refresh_values(vars_local)

        # Recurse into children
        for child in getattr(node, "children", []):
            child_vars, _ = self.execute(
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

            nxt = child_vars.get("__GH_NEXT_CHILD_TEMPLATE__", None)
            if nxt is not None:
                ns_effective.child_template = (nxt or None)

        self._env.refresh_values(vars_local)

        # Template rendering
        rendered = dump_raw
        chosen_tpl = ns_effective.template or parent_child_tpl
        if chosen_tpl:
            tpl_path = self._paths.resolve(workspace, chosen_tpl)
            if not tpl_path.exists():
                self._fatal(f"template {tpl_path} not found")
            rendered = self._rend.render_template(
                tpl_path.read_text(encoding="utf-8"),
                {**vars_local, "ghconcat_dump": "".join(gh_dump or [])},
            )

        if ctx_name:
            vars_local[f"_t_{ctx_name}"] = rendered
            vars_local[ctx_name] = rendered

        self._env.refresh_values(vars_local)

        # AI integration
        final_out = rendered
        out_path: Optional[Path] = None
        if ns_effective.output and ns_effective.output.lower() != TOK_NONE:
            out_path = self._paths.resolve(workspace, ns_effective.output)

        if ns_effective.ai:
            if out_path is None:
                tf = tempfile.NamedTemporaryFile(delete=False, dir=workspace, suffix=".ai.txt")
                tf.close()
                out_path = Path(tf.name)

            sys_prompt = ""
            if (ns_effective.ai_system_prompt and ns_effective.ai_system_prompt.lower() != TOK_NONE):
                spath = self._paths.resolve(workspace, ns_effective.ai_system_prompt)
                if not spath.exists():
                    self._fatal(f"system prompt {spath} not found")
                sys_prompt = self._rend.render_template(spath.read_text(encoding="utf-8"), vars_local)

            seeds = None
            if (ns_effective.ai_seeds and ns_effective.ai_seeds.lower() != TOK_NONE):
                seeds = self._paths.resolve(workspace, ns_effective.ai_seeds)

            self._ai.run(
                rendered,
                out_path,
                model=ns_effective.ai_model,
                system_prompt=sys_prompt,
                temperature=ns_effective.ai_temperature,
                top_p=ns_effective.ai_top_p,
                presence_pen=ns_effective.ai_presence_penalty,
                freq_pen=ns_effective.ai_frequency_penalty,
                seeds_path=seeds,
                max_tokens=getattr(ns_effective, "ai_max_tokens", None),
                reasoning_effort=getattr(ns_effective, "ai_reasoning_effort", None),
            )
            final_out = out_path.read_text(encoding="utf-8")

        if ctx_name:
            vars_local[f"_ia_{ctx_name}"] = final_out
            vars_local[ctx_name] = final_out

        self._env.refresh_values(vars_local)

        # Persist to -o (non-AI case) + stdout rules
        if out_path and not ns_effective.ai:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(final_out, encoding="utf-8")
            self._log.info("✔ Output written → %s", out_path)

        force_stdout = getattr(ns_effective, "to_stdout", False)
        auto_root_stdout = (level == 0 and ns_effective.output in (None, TOK_NONE))
        if force_stdout or (auto_root_stdout and not force_stdout):
            if not sys.stdout.isatty():
                sys.stdout.write(final_out)
            else:
                print(final_out, end="")

        if level == 0 and final_out == "" and gh_dump:
            final_out = "".join(gh_dump)
        if level == 0 and gh_dump is not None:
            vars_local["ghconcat_dump"] = "".join(gh_dump)

        vars_local["__GH_NEXT_CHILD_TEMPLATE__"] = child_tpl_for_descendants or ""

        return vars_local, final_out

    # ---- Internals ------------------------------------------------------

    def _merge_ns(self, parent: Optional[argparse.Namespace], child: argparse.Namespace) -> argparse.Namespace:
        """Mirror ghconcat._merge_ns behavior (child overrides, lists extend)."""
        if parent is None:
            return child
        merged = deepcopy(vars(parent))
        from .ghconcat import _LIST_ATTRS, _BOOL_ATTRS, _INT_ATTRS, _FLT_ATTRS, _STR_ATTRS, _NON_INHERITED  # lazy import to avoid cycle

        for key, val in vars(child).items():
            if key in _NON_INHERITED:
                merged[key] = val
                continue
            if key in _LIST_ATTRS:
                merged[key] = [*(merged.get(key) or []), *(val or [])]
            elif key in _BOOL_ATTRS:
                merged[key] = val or merged.get(key, False)
            elif key in _INT_ATTRS | _FLT_ATTRS:
                merged[key] = val if val is not None else merged.get(key)
            elif key in _STR_ATTRS:
                merged[key] = val if val not in (None, "") else merged.get(key)
            else:
                merged[key] = val

        ns = argparse.Namespace(**merged)
        self._post_parse(ns)
        return ns

    @staticmethod
    def _split_list(raw: Optional[List[str]]) -> List[str]:
        """Split comma/space-separated tokens into a flat list."""
        if not raw:
            return []
        out: List[str] = []
        for itm in raw:
            out.extend([x for x in re.split(r"[,\s]+", itm) if x])
        return out

    def _fatal(self, msg: str, code: int = 1) -> None:
        """Abort execution immediately with *msg*."""
        self._log.error(msg)
        raise SystemExit(code)


# ----- Default wiring helpers (used by GhConcat.run) ------------------------

def make_default_walker(header_delim: str, seen_files: Set[str], logger: logging.Logger) -> WalkerAppender:
    """Return a WalkerAppender wired to ghconcat's global readers and filters."""
    # We import local helpers from ghconcat to avoid duplication and keep behavior.
    from .ghconcat import _read_file_as_lines, _html_to_text, _apply_replacements, _slice, _clean  # noqa: WPS433
    return WalkerAppender(
        read_file_as_lines=_read_file_as_lines,
        html_to_text=_html_to_text,
        apply_replacements=_apply_replacements,
        slice_lines=_slice,
        clean_lines=_clean,
        header_delim=header_delim,
        seen_files=seen_files,
        logger=logger,
    )