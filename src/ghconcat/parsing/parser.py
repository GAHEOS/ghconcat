# ghconcat/parsing/parser.py
from __future__ import annotations

import argparse

DEFAULT_OPENAI_MODEL = "o3"


def _build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for a single context block.

    Notes:
        - This parser exposes only the effective flags required by the runtime.
        - Help texts reflect the current (v2) semantics and are mapped from
          legacy docs when applicable. No deprecated flags are introduced here.
    """
    p = argparse.ArgumentParser(
        prog="ghconcat",
        formatter_class=argparse.RawTextHelpFormatter,
        usage="%(prog)s [-x FILE] … [OPTIONS]",
        add_help=False,
        description=(
            "ghconcat – multi-level concatenation, slicing & templating tool\n"
            "Everything after a “-x FILE” is parsed inside the directive-file "
            "context unless another “-x” is encountered."
        ),
    )

    g_loc = p.add_argument_group("Discovery")
    g_rng = p.add_argument_group("Line slicing")
    g_cln = p.add_argument_group("Cleaning")
    g_sub = p.add_argument_group("Substitution")
    g_tpl = p.add_argument_group("Template & output")
    g_ai = p.add_argument_group("AI integration")
    g_misc = p.add_argument_group("Miscellaneous")

    # -----------------------
    # Discovery
    # -----------------------
    g_loc.add_argument(
        "-w",
        "--workdir",
        metavar="DIR",
        dest="workdir",
        help=(
            "Root directory to scan for content files in the current context. "
            "If omitted, the current working directory is used. Other relative "
            "paths (templates, outputs, -a PATH, etc.) resolve against this directory "
            "unless a parent context re-defines it."
        ),
    )
    g_loc.add_argument(
        "-W",
        "--workspace",
        metavar="DIR",
        dest="workspace",
        help=(
            "Workspace folder for templates, prompts, AI artifacts and outputs. "
            "Defaults to the current -w directory. Paths passed to -o/-t/--ai-* "
            "are resolved here to keep sources and generated files separated."
        ),
    )
    g_loc.add_argument(
        "-a",
        "--add-path",
        metavar="PATH",
        action="append",
        dest="add_path",
        help=(
            "Add a file OR a directory (recursively) to the inclusion set. Repeatable. "
            "Bare CLI tokens that do not start with '-' are implicitly treated as '-a PATH', "
            "EXCEPT tokens recognized as URLs or Git SPECs, which are handled by their "
            "dedicated ingestors (control URL recursion with --url-depth)."
        ),
    )
    g_loc.add_argument(
        "-A",
        "--exclude-path",
        metavar="DIR",
        action="append",
        dest="exclude_path",
        help=(
            "Exclude an entire directory subtree from discovery, overriding broader "
            "inclusion rules. Repeatable and applied before suffix filters."
        ),
    )
    g_loc.add_argument(
        "--url-depth",
        metavar="N",
        type=int,
        dest="url_depth",
        default=0,
        help=(
            "Depth for URL crawling (0 = fetch-only; >0 = breadth-first scrape). "
            "Tokens recognized as URLs are auto-classified; use this to control recursion."
        ),
    )
    g_loc.add_argument(
        "--url-allow-cross-domain",
        action="store_true",
        dest="url_cross_domain",
        help=(
            "Allow the scraper to follow links outside the seed's scheme+host. "
            "Disabled by default to confine crawling to the original domain."
        ),
    )
    g_loc.add_argument(
        "--url-policy",
        metavar="module:Class",
        dest="url_policy_ref",
        help="Custom UrlAcceptPolicy implementation (advanced).",
        default=None,
    )
    g_loc.add_argument(
        "-s",
        "--suffix",
        metavar="SUF",
        action="append",
        dest="suffix",
        help=(
            "Whitelist extensions (e.g. '.py'). If at least one -s is present, the "
            "filter becomes allow-only (other extensions are ignored unless explicitly "
            "allowed by another rule). Repeatable."
        ),
    )
    g_loc.add_argument(
        "-S",
        "--exclude-suffix",
        metavar="SUF",
        action="append",
        dest="exclude_suf",
        help=(
            "Blacklist extensions irrespective of origin (local or remote). "
            "An explicit file added with -a always wins over exclusion suffixes; "
            "URL/Git resources still honor suffix filters during fetch/scrape."
        ),
    )

    # -----------------------
    # Line slicing
    # -----------------------
    g_rng.add_argument(
        "-n",
        "--total-lines",
        metavar="NUM",
        type=int,
        dest="total_lines",
        help=(
            "Keep at most NUM lines from each file after header adjustments. "
            "Combine with -N to define sliding windows."
        ),
    )
    g_rng.add_argument(
        "-N",
        "--start-line",
        metavar="LINE",
        type=int,
        dest="first_line",
        help=(
            "Start concatenation at the given 1-based line number. Lines before this "
            "may be kept or dropped according to -m / -M."
        ),
    )
    g_rng.add_argument(
        "-m",
        "--keep-first-line",
        dest="first_flags",
        action="append_const",
        const="keep",
        help=(
            "Always retain the very first physical line (shebang, encoding cookie, "
            "XML prolog, etc.) even if slicing starts later."
        ),
    )
    g_rng.add_argument(
        "-M",
        "--no-first-line",
        dest="first_flags",
        action="append_const",
        const="drop",
        help="Force-drop the first physical line regardless of other slicing flags.",
    )

    # -----------------------
    # Substitution
    # -----------------------
    g_sub.add_argument(
        "-y",
        "--replace",
        metavar="SPEC",
        action="append",
        dest="replace_rules",
        help=(
            "Delete or substitute text fragments that match SPEC. Syntax:\n"
            "  `/pattern/`                 → delete matches\n"
            "  `/pattern/repl/flags`       → substitute (flags ∈ {g,i,m,s})\n"
            "Delimiter is `/` and may be escaped with `\\/`. Pattern is a Python regex. "
            "Invalid patterns are logged and ignored."
        ),
    )
    g_sub.add_argument(
        "-Y",
        "--preserve",
        metavar="SPEC",
        action="append",
        dest="preserve_rules",
        help=(
            "Regex exceptions for -y. Any region matched by a PRESERVE rule is "
            "shielded from the replace engine and restored afterwards. Same syntax/flags as -y."
        ),
    )

    # -----------------------
    # Cleaning
    # -----------------------
    g_cln.add_argument(
        "-c",
        "--remove-comments",
        action="store_true",
        dest="rm_comments",
        help=(
            "Remove comments (inline and full-line) and, where applicable, language "
            "docstrings (e.g., Python triple-quoted). Language-aware strippers are used "
            "when available. Use -C to cancel in a child context."
        ),
    )
    g_cln.add_argument(
        "-C",
        "--no-remove-comments",
        action="store_true",
        dest="no_rm_comments",
        help="Cancel comment/docstring removal in this context (overrides an inherited -c).",
    )
    g_cln.add_argument(
        "-i",
        "--remove-import",
        action="store_true",
        dest="rm_import",
        help="Strip import-like statements where supported (import/require/include/use/#include).",
    )
    g_cln.add_argument(
        "-I",
        "--remove-export",
        action="store_true",
        dest="rm_export",
        help="Strip export declarations where supported (e.g., JS/TS 'export', 'module.exports').",
    )
    g_cln.add_argument(
        "-b",
        "--strip-blank",
        dest="blank_flags",
        action="append_const",
        const="strip",
        help="Delete blank lines left after cleaning.",
    )
    g_cln.add_argument(
        "-B",
        "--keep-blank",
        dest="blank_flags",
        action="append_const",
        const="keep",
        help="Preserve blank lines (overrides an inherited -b).",
    )
    g_cln.add_argument(
        "-K",
        "--textify-html",
        action="store_true",
        dest="strip_html",
        help="Convert .html/.htm/.xhtml files to plain text (tags removed) before concatenation.",
    )

    # -----------------------
    # Template & output
    # -----------------------
    g_tpl.add_argument(
        "-t",
        "--template",
        metavar="FILE",
        dest="template",
        help=(
            "Render the current context through a minimalist brace-based template. "
            "Placeholders have access to per-context variables, `ghconcat_dump`, and -e/-E values. "
            "Not inherited."
        ),
    )
    g_tpl.add_argument(
        "-T",
        "--child-template",
        metavar="FILE",
        dest="child_template",
        help=(
            "Set a default template for descendant contexts only. If both -t and -T are present, "
            "-t applies locally while -T updates the default for subsequent contexts. Children can "
            "override the inherited -T by specifying their own -t or replace it with a new -T."
        ),
    )
    g_tpl.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        dest="output",
        help=(
            "Write the final text to FILE (resolved against the workspace). "
            "If omitted at the root context, the result streams to STDOUT."
        ),
    )
    g_tpl.add_argument(
        "-O",
        "--stdout",
        action="store_true",
        dest="to_stdout",
        help="Also duplicate the final output to STDOUT even when -o is present.",
    )
    g_tpl.add_argument(
        "-u",
        "--wrap",
        metavar="LANG",
        dest="wrap_lang",
        help=(
            "Wrap each file body in a fenced code block. The info string defaults to LANG; "
            "pass an empty string to keep language-less fences."
        ),
    )
    g_tpl.add_argument(
        "-U",
        "--no-wrap",
        action="store_true",
        dest="unwrap",
        help="Cancel any inherited -u/--wrap directive in this child context.",
    )
    g_tpl.add_argument(
        "-h",
        "--header",
        dest="hdr_flags",
        action="append_const",
        const="show",
        help="Emit a banner header before each new file (`===== path =====`).",
    )
    g_tpl.add_argument(
        "-H",
        "--no-headers",
        dest="hdr_flags",
        action="append_const",
        const="hide",
        help="Suppress banner headers in this scope (child contexts may re-enable).",
    )
    g_tpl.add_argument(
        "-r",
        "--relative-path",
        dest="path_flags",
        action="append_const",
        const="relative",
        help="Show header paths relative to the current workdir (default).",
    )
    g_tpl.add_argument(
        "-R",
        "--absolute-path",
        dest="path_flags",
        action="append_const",
        const="absolute",
        help="Show header paths as absolute file-system paths.",
    )
    g_tpl.add_argument(
        "-l",
        "--list",
        action="store_true",
        dest="list_only",
        help="List matching file paths instead of their contents (one per line).",
    )
    g_tpl.add_argument(
        "-L",
        "--no-list",
        action="store_true",
        dest="no_list",
        help="Disable an inherited list mode within this context.",
    )
    g_tpl.add_argument(
        "-e",
        "--env",
        metavar="VAR=VAL",
        action="append",
        dest="env_vars",
        help=(
            "Define a local placeholder visible only in the current context. "
            "Placeholders may reference earlier ones using the `$VAR` syntax."
        ),
    )
    g_tpl.add_argument(
        "-E",
        "--global-env",
        metavar="VAR=VAL",
        action="append",
        dest="global_env",
        help=(
            "Define a global placeholder inherited by every descendant context. "
            "May be overridden locally with -e."
        ),
    )

    # -----------------------
    # AI
    # -----------------------
    g_ai.add_argument(
        "--ai",
        action="store_true",
        help=(
            "Send the rendered text to an OpenAI-compatible endpoint. Requires "
            "OPENAI_API_KEY in the environment. The AI reply is written to -o "
            "(or to a temp file if -o is absent) and exposed as `{_ia_ctx}`."
        ),
    )
    g_ai.add_argument(
        "--ai-model",
        metavar="MODEL",
        default=DEFAULT_OPENAI_MODEL,
        dest="ai_model",
        help="Model to use (default: o3).",
    )
    g_ai.add_argument(
        "--ai-temperature",
        type=float,
        metavar="NUM",
        dest="ai_temperature",
        help="Sampling temperature for chat models (range 0–2).",
    )
    g_ai.add_argument(
        "--ai-top-p",
        type=float,
        metavar="NUM",
        dest="ai_top_p",
        help="Top-p nucleus sampling parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-presence-penalty",
        type=float,
        metavar="NUM",
        dest="ai_presence_penalty",
        help="Presence-penalty parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-frequency-penalty",
        type=float,
        metavar="NUM",
        dest="ai_frequency_penalty",
        help="Frequency-penalty parameter (chat models).",
    )
    g_ai.add_argument(
        "--ai-system-prompt",
        metavar="FILE",
        dest="ai_system_prompt",
        help="Template-aware system prompt file to prepend to the chat.",
    )
    g_ai.add_argument(
        "--ai-seeds",
        metavar="FILE",
        dest="ai_seeds",
        help="JSONL file with seed messages to prime the chat.",
    )
    g_ai.add_argument(
        "--ai-max-tokens",
        type=int,
        metavar="NUM",
        dest="ai_max_tokens",
        help=(
            "Maximum output tokens. For reasoning models (o-series, gpt-5 base) maps "
            "to `max_output_tokens` (Responses API). For chat models (gpt-4o*, "
            "gpt-5-chat*) maps to `max_tokens` (Chat Completions)."
        ),
    )
    g_ai.add_argument(
        "--ai-reasoning-effort",
        metavar="LEVEL",
        dest="ai_reasoning_effort",
        choices=("low", "medium", "high"),
        help=(
            "Reasoning effort for o-series/gpt-5 (Responses API). "
            "Ignored by chat models. Defaults to GHCONCAT_AI_REASONING_EFFORT or 'medium'."
        ),
    )

    # -----------------------
    # Misc
    # -----------------------
    g_misc.add_argument(
        "--preserve-cache",
        action="store_true",
        help="Keep the .ghconcat_*cache directories after finishing the run.",
    )
    g_misc.add_argument(
        "--upgrade",
        action="store_true",
        help="Self-update ghconcat from the official repository into ~/.bin.",
    )
    g_misc.add_argument(
        "--json-logs",
        action="store_true",
        dest="json_logs",
        help="Emit logs in JSON format instead of plain text.",
    )
    g_misc.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    g_misc.add_argument(
        "--classifier",
        metavar="REF",
        dest="classifier_ref",
        help=(
            'Custom classifier as "module.path:ClassName" or "none". '
            "If omitted, the default classifier is used. You may also set "
            "the GHCONCAT_CLASSIFIER environment variable."
        ),
    )
    g_misc.add_argument(
        "--classifier-policies",
        metavar="NAME",
        dest="classifier_policies",
        choices=("standard", "none"),
        default="standard",
        help='Policy preset to register on the classifier (default: "standard").',
    )

    return p