from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ghconcat.core.interfaces.ai import AIProcessorProtocol
from ghconcat.core.interfaces.classifier import InputClassifierProtocol
from ghconcat.core.interfaces.fs import FileDiscoveryProtocol, PathResolverProtocol
from ghconcat.core.interfaces.render import RendererProtocol
from ghconcat.core.report import ExecutionReport, StageTimer
from ghconcat.io.html_reader import HtmlToTextReader
from ghconcat.io.reader_context import ReaderMappingScope
from ghconcat.io.readers import ReaderRegistry, get_global_reader_registry
from ghconcat.parsing.directives import DirNode
from ghconcat.parsing.list_ops import split_list
from ghconcat.processing.input_classifier import DefaultInputClassifier
from ghconcat.core.models import ContextConfig
from ghconcat.runtime.flag_mapping import flags_to_argv
from ghconcat.ai.token_budget import TokenBudgetEstimator
from ghconcat.ai.message_utils import build_chat_messages
from ghconcat.ai.model_registry import context_window_for
from ghconcat.logging.helpers import get_logger


class ExecutionEngine:
    """High-level execution engine that wires together parsing, discovery,
    templating and optional AI post-processing."""

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
        classifier: Optional[InputClassifierProtocol] = None,
        report: Optional[ExecutionReport] = None,
    ) -> None:
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
        self._log = logger or get_logger("exec")
        self._report = report or ExecutionReport()

        if registry is not None:
            self._registry = registry
        elif registry_factory is not None:
            self._registry = registry_factory()
        else:
            self._registry = get_global_reader_registry(self._log).clone_suffix_only()

        self._read_file_as_lines = lambda fp: self._registry.read_lines(fp)
        self._strict_ws = os.getenv("GHCONCAT_STRICT_WS") == "1"
        self._classifier: InputClassifierProtocol = classifier or DefaultInputClassifier()

    def _resolve_root_and_workspace(
        self,
        ns_parent: Optional[argparse.Namespace],
        ns_self: argparse.Namespace,
        parent_root: Optional[Path],
        parent_workspace: Optional[Path],
    ) -> tuple[Path, Path]:
        if ns_parent is None:
            base_for_root = Path.cwd()
            root = self._resolver.resolve(base_for_root, ns_self.workdir or ".")
        elif ns_self.workdir not in (None, ""):
            base_for_root = parent_root or Path.cwd()
            root = self._resolver.resolve(base_for_root, ns_self.workdir)
        else:
            root = parent_root or Path.cwd()

        if ns_parent is None:
            if ns_self.workspace not in (None, ""):
                workspace = self._resolver.resolve(root, ns_self.workspace)
            else:
                workspace = root
        elif ns_self.workspace not in (None, ""):
            base_ws = parent_workspace or root
            workspace = self._resolver.resolve(base_ws, ns_self.workspace)
        else:
            workspace = parent_workspace or root
        return (root, workspace)

    def _configure_resolver_workspace(self, workspace: Path) -> None:
        try:
            setter = getattr(self._resolver, "set_workspace_root", None)
            if callable(setter):
                setter(workspace)
        except Exception:
            pass

    def _guard_ws(self, path: Path) -> Path:
        if self._strict_ws and (not self._resolver.is_within_workspace(path)):
            self._fatal(f"unsafe path outside workspace: {path}")
            raise SystemExit(1)
        return path

    def _enter_html_reader_scope(
        self, ns_effective: argparse.Namespace
    ) -> Optional[ReaderMappingScope]:
        if not getattr(ns_effective, "strip_html", False):
            return None
        scope = ReaderMappingScope(self._registry)
        scope.__enter__()
        scope.register([".html", ".htm", ".xhtml"], HtmlToTextReader(logger=self._log))
        return scope

    @staticmethod
    def _resolve_model_ctx_window(model: str | None) -> int | None:
        """Return the model context window using the centralized registry."""
        return context_window_for(model or "")

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
        # ... (unchanged engine logic except logging and ctx-window retrieval)
        inherited_vars = inherited_vars or {}
        tokens = self._expand_tokens(node.tokens, inherited_env=inherited_vars)
        ns_self = self._parser_factory().parse_args(tokens)
        self._post_parse(ns_self)
        ns_effective = self._merge_ns(ns_parent, ns_self) if ns_parent else ns_self

        if level == 0:
            gh_dump = []

        root, workspace = self._resolve_root_and_workspace(
            ns_parent, ns_self, parent_root, parent_workspace
        )
        self._configure_resolver_workspace(workspace)
        self._workspaces_seen.add(workspace)
        ns_effective.workspace = str(workspace)

        self._report.mark_context(root=root, workspace=workspace)

        if not root.exists():
            msg = f"--workdir {root} not found"
            self._report.add_error(msg)
            self._fatal(msg)
            raise SystemExit(1)

        if not workspace.exists():
            msg = f"--workspace {workspace} not found"
            self._report.add_error(msg)
            self._fatal(msg)
            raise SystemExit(1)

        maybe_scope = self._enter_html_reader_scope(ns_effective)
        try:
            dump_raw = ""
            self._classifier.reclassify(ns_effective)

            if ns_effective.add_path or ns_effective.git_path or ns_effective.urls or ns_effective.url_scrape:
                suffixes = split_list(getattr(ns_effective, "suffix", None))
                exclude_suf = split_list(getattr(ns_effective, "exclude_suf", None))

                with StageTimer(self._report, "local_discovery"):
                    local_files = self._discovery.gather_local(
                        add_paths=ns_effective.add_path,
                        exclude_paths=ns_effective.exclude_path,
                        suffixes=suffixes,
                        exclude_suf=exclude_suf,
                        root=root,
                    )
                self._report.add_paths(local_files, source="local")

                with StageTimer(self._report, "git_collect"):
                    git_files = self._discovery.collect_git(
                        git_specs=ns_effective.git_path,
                        git_exclude=ns_effective.git_exclude,
                        workspace=workspace,
                        suffixes=suffixes,
                        exclude_suf=exclude_suf,
                    )
                self._report.add_paths(git_files, source="git")

                with StageTimer(self._report, "url_fetch"):
                    remote_files = self._discovery.fetch_urls(
                        urls=ns_effective.urls, workspace=workspace
                    )
                self._report.add_paths(remote_files, source="url")

                with StageTimer(self._report, "url_scrape"):
                    scraped_files = self._discovery.scrape_urls(
                        seeds=ns_effective.url_scrape,
                        workspace=workspace,
                        suffixes=suffixes,
                        exclude_suf=exclude_suf,
                        max_depth=getattr(ns_effective, "url_depth", 0) or 0,
                        same_host_only=not getattr(ns_effective, "url_cross_domain", False),
                    )
                self._report.add_paths(scraped_files, source="scrape")

                files = [*local_files, *remote_files, *scraped_files, *git_files]
                if files:
                    with StageTimer(self._report, "concat"):
                        dump_raw = self._renderer.concat(
                            files, ns_effective, header_root=root
                        )
        finally:
            if maybe_scope is not None:
                maybe_scope.__exit__(None, None, None)

        ctx_name = node.name
        global_env_map = self._parse_env_items(getattr(ns_effective, "global_env", None))
        local_env_map = self._parse_env_items(getattr(ns_effective, "env_vars", None))
        inherited_for_children = {**(inherited_vars or {}), **global_env_map}
        vars_local = {**inherited_for_children, **local_env_map}

        if ctx_name:
            vars_local[f"_r_{ctx_name}"] = dump_raw
            vars_local[ctx_name] = dump_raw

        if gh_dump is not None:
            gh_dump.append(dump_raw)

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
            nxt = child_vars.get("__GH_NEXT_CHILD_TEMPLATE__", None)
            if nxt is not None:
                ns_effective.child_template = nxt or None

        rendered = dump_raw
        parent_child_tpl = getattr(ns_parent, "child_template", None) if ns_parent else None
        chosen_tpl = getattr(ns_effective, "template", None) or parent_child_tpl
        if chosen_tpl:
            tpl_path = self._resolver.resolve(workspace, chosen_tpl)
            tpl_path = self._guard_ws(tpl_path)
            if not tpl_path.exists():
                msg = f"template {tpl_path} not found"
                self._report.add_error(msg)
                self._fatal(msg)
                raise SystemExit(1)
            with StageTimer(self._report, "template"):
                rendered = self._renderer.render_template(tpl_path, vars_local, "".join(gh_dump or []))

        if ctx_name:
            vars_local[f"_t_{ctx_name}"] = rendered
            vars_local[ctx_name] = rendered

        final_out = rendered
        out_path: Optional[Path] = None
        out_val = getattr(ns_effective, "output", None)
        if out_val not in (None, "") and str(out_val).lower() != "none":
            out_path = self._resolver.resolve(workspace, out_val)
            out_path = self._guard_ws(out_path)

        if getattr(ns_effective, "ai", False):
            if out_path is None:
                tf = tempfile.NamedTemporaryFile(delete=False, dir=workspace, suffix=".ai.txt")
                tf.close()
                out_path = Path(tf.name)

            sys_prompt = ""
            ai_sys = getattr(ns_effective, "ai_system_prompt", None)
            if ai_sys and str(ai_sys).lower() != "none":
                spath = self._resolver.resolve(workspace, ai_sys)
                spath = self._guard_ws(spath)
                if not spath.exists():
                    msg = f"system prompt {spath} not found"
                    self._report.add_error(msg)
                    self._fatal(msg)
                    raise SystemExit(1)
                sys_prompt = self._renderer.interpolate(
                    spath.read_text(encoding="utf-8"), vars_local
                )

            seeds_path = None
            ai_seeds = getattr(ns_effective, "ai_seeds", None)
            if ai_seeds and str(ai_seeds).lower() != "none":
                seeds_path = self._resolver.resolve(workspace, ai_seeds)
                seeds_path = self._guard_ws(seeds_path)

            # Token metrics preview (pre-call)
            try:
                messages = build_chat_messages(
                    system_prompt=sys_prompt, seeds_path=seeds_path, user_prompt=rendered
                )
                model_name = getattr(ns_effective, "ai_model", "") or ""
                ctx_window = self._resolve_model_ctx_window(model_name)
                estimator = TokenBudgetEstimator()
                est = estimator.estimate_messages_tokens(
                    messages, model=model_name, context_window=ctx_window
                )
                self._report.ai_tokens_in = est.tokens_in
                self._report.ai_model_ctx_window = ctx_window
            except Exception:
                pass

            # AI call
            with StageTimer(self._report, "ai"):
                self._ai.run(
                    prompt=rendered,
                    out_path=out_path,
                    model=getattr(ns_effective, "ai_model", ""),
                    system_prompt=sys_prompt,
                    temperature=getattr(ns_effective, "ai_temperature", None),
                    top_p=getattr(ns_effective, "ai_top_p", None),
                    presence_penalty=getattr(ns_effective, "ai_presence_penalty", None),
                    frequency_penalty=getattr(ns_effective, "ai_frequency_penalty", None),
                    seeds_path=seeds_path,
                    max_tokens=getattr(ns_effective, "ai_max_tokens", None),
                    reasoning_effort=getattr(ns_effective, "ai_reasoning_effort", None),
                )

            final_out = out_path.read_text(encoding="utf-8")

            # Token metrics post-call (best-effort)
            try:
                model_name = getattr(ns_effective, "ai_model", "") or ""
                estimator = TokenBudgetEstimator()
                self._report.ai_tokens_out = estimator.estimate_text_tokens(final_out, model=model_name)
            except Exception:
                pass

            # Sidecar meta (optional)
            try:
                meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    usage = meta.get("usage") or {}
                    self._report.ai_finish_reason = meta.get("finish_reason")
                    self._report.ai_usage_prompt = usage.get("prompt_tokens")
                    self._report.ai_usage_completion = usage.get("completion_tokens")
                    self._report.ai_usage_total = usage.get("total_tokens")
            except Exception:
                pass

        if ctx_name:
            vars_local[f"_ia_{ctx_name}"] = final_out
            vars_local[ctx_name] = final_out

        if out_path and (not getattr(ns_effective, "ai", False)):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(final_out, encoding="utf-8")
            self._log.info("✔ Output written → %s", out_path)

        force_stdout = bool(getattr(ns_effective, "to_stdout", False))
        auto_root_stdout = level == 0 and getattr(ns_effective, "output", None) in (None, "none")
        if force_stdout or (auto_root_stdout and (not force_stdout)):
            if not sys.stdout.isatty():
                sys.stdout.write(final_out)
            else:
                print(final_out, end="")

        if level == 0 and final_out == "" and gh_dump:
            final_out = "".join(gh_dump)

        if level == 0 and gh_dump is not None:
            vars_local["ghconcat_dump"] = "".join(gh_dump)

        vars_local["__GH_NEXT_CHILD_TEMPLATE__"] = getattr(ns_effective, "child_template", None) or ""

        if level == 0:
            self._report.finish()
            report_target = getattr(ns_effective, "report_json", None)
            if report_target not in (None, "", "none"):
                target = Path(str(report_target))
                if str(target) == "-":
                    print(self._report.to_json(), file=sys.stderr)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(self._report.to_json() + "\n", encoding="utf-8")
                    self._log.info("✔ Report written → %s", target)

        return (vars_local, final_out)

    # run / run_with_report stay unchanged (defined elsewhere in runtime)

    def run(self, ctx: ContextConfig) -> str:
        node = DirNode(name=ctx.name or None, tokens=self._tokens_from_context(ctx))
        _vars, out = self.execute_node(node, None)
        return out

    def run_with_report(self, ctx: ContextConfig) -> tuple[str, ExecutionReport]:
        out = self.run(ctx)
        return (out, self._report)