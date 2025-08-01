#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full functional test‑suite for *ghconcat* (spec v2, 2025‑08‑01).

Every CLI switch is exercised; OpenAI calls are mocked so the battery
runs completely offline.

All docstrings and inline comments are written in English, as required
by the project’s coding standards.
"""
from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Iterator, List
from unittest.mock import patch

# --------------------------------------------------------------------------- #
#  Dynamic import (works with editable installs and repo check-out)           #
# --------------------------------------------------------------------------- #
try:
    from ghconcat.src import ghconcat
except ModuleNotFoundError:  # pragma: no cover
    import sys

    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from ghconcat.src import ghconcat

GhConcat = ghconcat.GhConcat  # type: ignore
HEADER_DELIM = ghconcat.HEADER_DELIM  # type: ignore

# --------------------------------------------------------------------------- #
#  Helpers & constants                                                        #
# --------------------------------------------------------------------------- #
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "test-fixtures"
DUMP = FIXTURES / "dump.txt"
INLINE_FILES = ["inline1.gcx", "inline2.gcx", "inline3.gcx"]
BATCH_FILES = ["batch1.gcx", "batch2.gcx", "batch3.gcx"]


@contextlib.contextmanager
def _inside_fixtures() -> Iterator[None]:
    """Temporarily switch the current working directory to the fixture root."""
    cwd = Path.cwd()
    os.chdir(FIXTURES)
    try:
        yield
    finally:
        os.chdir(cwd)


def _run(args: List[str]) -> str:
    """
    Execute *ghconcat* with *args* and return its final output string.

    If the caller does not provide ``-w/--workdir`` nor uses an ``-x``
    directive, the helper injects ``-w FIXTURES`` automatically so all
    path resolutions stay inside the fixture tree.
    """
    base = list(args)
    if "-x" not in base and all(f not in ("-w", "--workdir") for f in base):
        base += ["-w", str(FIXTURES)]

    with _inside_fixtures():
        return GhConcat.run(base)


def _extract_segment(dump: str, filename: str) -> str:
    """
    Return the chunk in *dump* that belongs to *filename*.
    """
    pat = re.compile(
        rf"{re.escape(HEADER_DELIM)}[^\n]*{re.escape(filename)}[^\n]*\n", re.M
    )
    m = pat.search(dump)
    if not m:
        return ""
    start = m.end()
    nxt = dump.find(HEADER_DELIM, start)
    return dump[start:nxt if nxt != -1 else None]


# --------------------------------------------------------------------------- #
#  Fixture generation                                                         #
# --------------------------------------------------------------------------- #
def _ensure_directive_fixtures() -> None:
    """
    Create *.gcx* directive files and workspaces on‑the‑fly when absent.

    The contents have been updated to the final CLI (spec v2,
    2025‑08‑01): «‑O» for aliases, removal of «‑r», etc.
    """
    ws1 = FIXTURES / "ws1"
    ws2 = FIXTURES / "ws2"
    if not ws1.exists():
        (ws1 / "src/other").mkdir(parents=True, exist_ok=True)
        for src in (FIXTURES / "src/other").iterdir():
            shutil.copy2(src, ws1 / "src/other" / src.name)
    if not ws2.exists():
        (ws2 / "src/module").mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            FIXTURES / "src/module/echo.dart",
            ws2 / "src/module/echo.dart",
        )

    directives = {
        # inline level‑2 contexts (used via -X)
        "inline1.gcx": "-a src/module/charlie.js\n-g js\n-n 1\n-N 2\n",
        "inline2.gcx": "-a src/module/omega.xml\n-g xml\n-n 2\n",
        "inline3.gcx": "-a extra/sample.go\n-g go\n",
        # batch level‑2 contexts
        "batch1.gcx": "-w ws1\n-a src/other\n-g py\n-n 1\n-N 3\n",
        "batch2.gcx": "-a src\n-a other/delta.js\n-g js\n",
        "batch3.gcx": "-w ws2\n-a src\n-a module/echo.dart\n-g dart\n",
    }
    for name, body in directives.items():
        tgt = FIXTURES / name
        if not tgt.exists():
            tgt.write_text(body, encoding="utf-8")


class FixtureTreeMissing(Exception):
    """Raised when the fixture tree is absent."""


# --------------------------------------------------------------------------- #
#  Base class                                                                 #
# --------------------------------------------------------------------------- #
class GhConcatBaseTest(unittest.TestCase):
    """Utility mix‑in with common assertions used across all tests."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES.exists():
            raise FixtureTreeMissing(
                "Fixture tree not found. Run tests/tools/fixtures.sh first."
            )

    # shorthand assertions
    def assertInDump(self, member: str, dump: str, *, msg=None) -> None:
        self.assertIn(member, dump, msg or f"{member!r} not found in dump")

    def assertNotInDump(self, member: str, dump: str, *, msg=None) -> None:
        self.assertNotIn(member, dump, msg or f"{member!r} unexpectedly present")


# --------------------------------------------------------------------------- #
#  Test‑suites                                                                #
# --------------------------------------------------------------------------- #
class BasicBehaviourTests(GhConcatBaseTest):
    def test_basic_python_concat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            dump = _run(["-g", "py", "-a", "src/module", "-o", str(out)])
            self.assertInDump("alpha.py", dump)
            self.assertNotInDump("charlie.js", dump)
            self.assertTrue(out.exists())

    def test_skip_lang(self) -> None:
        dump = _run(["-g", "odoo", "-G", "js", "-a", "src/module"])
        self.assertNotInDump("charlie.js", dump)
        self.assertInDump("omega.xml", dump)


class CommentStrippingTests(GhConcatBaseTest):
    def _comment_removal(self, flag: str) -> None:
        dump = _run(["-g", "py", flag, "-a", "src/module/alpha.py"])
        self.assertNotInDump("# simple comment", dump)

    def test_c_removes_simple_comment(self) -> None:
        self._comment_removal("-c")

    def test_C_removes_all_comments(self) -> None:
        self._comment_removal("-C")

    def test_import_removal(self) -> None:
        dump = _run(["-g", "py", "-i", "-a", "src/module/alpha.py"])
        self.assertNotInDump("import os", dump)

    def test_export_removal(self) -> None:
        dump = _run(["-g", "js", "-I", "-a", "src/module/charlie.js"])
        self.assertNotInDump("export function", dump)


class RangeTests(GhConcatBaseTest):
    def test_range_n(self) -> None:
        dump = _run(["-g", "py", "-n", "10", "-a", "src/module/large.py"])
        self.assertEqual(dump.count("\n"), 11)  # header + 10 lines

    def test_range_nN_keep_header(self) -> None:
        dump = _run(["-g", "py", "-n", "50", "-N", "55", "-H",
                     "-a", "src/module/large.py"])
        lines = dump.splitlines()
        self.assertTrue(lines[1].startswith("# line 1"))
        numbered = [l for l in lines if l.startswith("# line ")]
        self.assertEqual(len(numbered), 51)

    def test_range_N_only(self) -> None:
        dump = _run(["-g", "py", "-N", "5", "-a", "src/module/large.py"])
        self.assertRegex(dump, r"(?m)^# line 5$")
        self.assertNotRegex(dump, r"(?m)^# line 4$")


class RouteAndBlankTests(GhConcatBaseTest):
    def test_route_only(self) -> None:
        dump = _run(["-g", "py", "-l", "-a", "src/module/alpha.py"])
        self.assertNotIn("def alpha", dump)

    def test_keep_blank(self) -> None:
        dump_no = _run(["-g", "py", "-a", "src/other/beta.py"])
        dump_yes = _run(["-g", "py", "-B", "-a", "src/other/beta.py"])
        self.assertGreater(len(dump_yes), len(dump_no))


class FilterTests(GhConcatBaseTest):
    def test_suffix_filter(self) -> None:
        dump = _run(["-g", "py", "-s", ".py", "-a", "src/module"])
        self.assertNotInDump("charlie.js", dump)
        self.assertInDump("alpha.py", dump)

    def test_additional_extension(self) -> None:
        dump = _run(["-g", "py", "-g", "go", "-a", "extra"])
        self.assertInDump("sample.go", dump)


class ExclusionTests(GhConcatBaseTest):
    def test_exclude_file(self) -> None:
        dump = _run(["-g", "py", "-a", ".", "-A", "exclude_me/ignored.py"])
        self.assertNotInDump("ignored.py", dump)

    def test_exclude_dir(self) -> None:
        dump = _run(["-g", "py", "-a", ".", "-A", "exclude_me"])
        self.assertNotInDump("ignored.py", dump)

    def test_hidden_files(self) -> None:
        dump = _run(["-g", "py", "-a", "."])
        self.assertNotInDump("secret.py", dump)


class DirectiveFileTests(GhConcatBaseTest):
    def test_inline_x_file(self) -> None:
        dump = _run(["-x", "inline.gcx"])
        self.assertInDump("alpha.py", dump)
        self.assertNotInDump("charlie.js", dump)

    def test_batch_X_file(self) -> None:
        dump = _run(["-g", "py", "-X", "batch.gcx", "-a", "src/module"])
        self.assertInDump("sample.go", dump)
        self.assertInDump("alpha.py", dump)


class AIIntegrationTests(GhConcatBaseTest):
    """
    Tests related to OpenAI integration.

    `_call_openai` is monkey‑patched so the suite never performs
    real HTTP requests.
    """

    def test_ai_template_and_wrap(self) -> None:
        """
        * `-u python` must wrap the dump in fences.
        * The dump is exposed via `-O code` and inserted in the template.
        * Therefore the prompt sent to OpenAI contains «```python».
        """
        tpl_path = FIXTURES / "ia_template.txt"
        tpl_path.write_text("### Context\n{code}\n", encoding="utf-8")

        def fake_call_openai(prompt: str, out_path: Path, *_args, **_kw) -> None:  # noqa: D401
            """Mock that writes a dummy reply so alias post‑processing succeeds."""
            out_path.write_text("FAKE_REPLY", encoding="utf-8")

        with tempfile.TemporaryDirectory() as td, \
                patch.object(ghconcat, "_call_openai", side_effect=fake_call_openai) as mocked, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            out = Path(td) / "ia_out.txt"
            _run([
                "-g", "py",
                "-O", "code",  # expose wrapped dump
                "-t", str(tpl_path),
                "--ai",
                "-u", "python",  # wrap
                "-o", str(out),
                "-a", "src/module/alpha.py",
            ])

            mocked.assert_called_once()
            prompt = mocked.call_args.args[0]

            # Validate wrap reached the prompt
            self.assertIn("```python", prompt)
            self.assertTrue(prompt.strip().endswith("```"))


class WorkspaceRootTests(GhConcatBaseTest):
    def test_workspace_and_root(self) -> None:
        root = FIXTURES / "src"
        dump = GhConcat.run([
            "-g", "py",
            "-w", str(root),  # workdir / root
            "-a", "module/alpha.py",
        ])
        self.assertIn("alpha.py", dump)


class UpgradeFlagTests(GhConcatBaseTest):
    def test_upgrade_dry_run(self) -> None:
        called: list[bool] = []

        def fake_upgrade() -> None:  # noqa: D401
            called.append(True)
            raise SystemExit(0)

        import importlib
        pkg = importlib.import_module("ghconcat")
        with patch.object(pkg, "_perform_upgrade", fake_upgrade):
            with self.assertRaises(SystemExit):
                GhConcat.run(["--upgrade"])
        self.assertTrue(called and called[0])

    def test_upgrade_with_extra_args_produces_exit(self) -> None:
        with self.assertRaises(SystemExit):
            GhConcat.run(["--upgrade", "-g", "py"])


class ExtraEdgeCaseTests(GhConcatBaseTest):
    def test_unknown_extension_inclusion(self) -> None:
        dump = _run(["-g", "fooext", "-a", "extra"])
        self.assertIn("sample.fooext", dump)

    def test_generated_dart_is_ignored(self) -> None:
        dump = _run(["-g", "dart", "-a", "build"])
        self.assertNotIn("ignore.g.dart", dump)

    def test_only_comments_file_is_skipped(self) -> None:
        dump = _run(["-g", "py", "-C", "-a", "src/module/only_comments.py"])
        self.assertNotIn("only_comments.py", dump)

    def test_file_explicit_included_must_be_applied_its_own_extension_rules(self) -> None:
        """
        If a file is explicitly included with an extension, it must be processed
        according to its own language rules, even if the main language is different.
        """
        dump = _run(["-C", "-a", "src/module/only_comments.py"])
        self.assertNotIn("only_comments.py", dump)

    def test_route_only_keeps_header(self) -> None:
        dump = _run(["-g", "js", "-l", "-a", "src/module/charlie.js"])
        self.assertIn("===== ", dump)
        self.assertNotIn("export function", dump)

    def test_absolute_exclude_dir(self) -> None:
        abs_dir = FIXTURES / "exclude_me"
        dump = _run(["-g", "py", "-a", ".", "-A", str(abs_dir)])
        self.assertNotInDump("ignored.py", dump)

    def test_skip_all_languages_fails(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-G", "py", "-a", "src"])


class CrossDirectiveCombinationTest(unittest.TestCase):
    """
    Verify that a deep mix of -X directive files runs correctly and that
    all child dumps are appended to the level‑0 output when no template
    is used at the top level.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES.exists():
            raise RuntimeError("Fixture tree missing. Run fixtures.sh first.")
        _ensure_directive_fixtures()

    def test_multi_level_directives(self) -> None:
        # level‑0 flags
        cli: List[str] = ["-g", "py"]
        # three inline .gcx files
        for xf in INLINE_FILES:
            cli += ["-X", xf]
        # three batch .gcx files
        for bf in BATCH_FILES:
            cli += ["-X", bf]
        # local path
        cli += ["-a", "src/module/alpha.py"]

        dump = _run(cli)

        expected = [
            "alpha.py", "charlie.js", "omega.xml", 'commented.js',
            "sample.go", "beta.py", "delta.js", "echo.dart", 'file with space.js'
        ]
        for fname in expected:
            with self.subTest(file=fname):
                self.assertIn(fname, dump)

        self.assertEqual(dump.count(HEADER_DELIM), len(expected) * 2)


# -------- NEW TESTS ---------------------------------------------------------- #
class HeaderSemanticsTests(GhConcatBaseTest):
    def test_H_ignored_when_N1(self) -> None:
        dump = _run(["-g", "py", "-N", "1", "-H", "-a", "src/module/large.py"])
        self.assertEqual(dump.splitlines()[1], "# line 1")

    def test_H_plus_N_and_n(self) -> None:
        dump = _run(["-g", "py", "-H", "-N", "40", "-n", "10",
                     "-a", "src/module/large.py"])
        lines = [l for l in dump.splitlines() if l.startswith("# line ")]
        self.assertEqual(lines[0], "# line 1")
        self.assertEqual(lines[1], "# line 40")
        self.assertEqual(len(lines), 11)


class AliasEnvTemplateTests(GhConcatBaseTest):
    def test_alias_and_env_interpolation(self) -> None:
        tpl = FIXTURES / "tpl.md"
        tpl.write_text("**{project}**\nPY:{py}\nGO:{go}\n", encoding="utf-8")

        # child contexts expose their dumps via aliases
        (FIXTURES / "py.gcx").write_text(
            "-a src/module/alpha.py\n-g py\n-O py\n", encoding="utf-8"
        )
        (FIXTURES / "go.gcx").write_text(
            "-a extra/sample.go\n-g go\n-O go\n", encoding="utf-8"
        )

        dump = _run(["-t", str(tpl), "-E", "project=Demo",
                     "-X", "py.gcx", "-X", "go.gcx"])
        self.assertIn("**Demo**", dump)
        self.assertIn("def alpha()", dump)
        self.assertIn("package main", dump)

    def test_invalid_env_pair_fails(self) -> None:
        bad_tpl = FIXTURES / "bad.tpl"
        bad_tpl.write_text("{dump_data}", encoding="utf-8")
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-E", "malformed", "-t", str(bad_tpl),
                  "-a", "src/module/alpha.py"])


class WrapBehaviourTests(GhConcatBaseTest):
    def test_wrap_without_body(self) -> None:
        dump = _run(["-g", "js", "-l", "-u", "js",
                     "-a", "src/module/charlie.js"])
        self.assertNotIn("```", dump)

    def test_wrap_content(self) -> None:
        dump = _run(["-g", "js", "-u", "javascript",
                     "-a", "src/module/charlie.js"])
        self.assertIn("```javascript", dump)
        self.assertTrue(dump.strip().endswith("```"))


class ErrorScenarioTests(GhConcatBaseTest):
    def test_multiple_x_allowed(self) -> None:
        (FIXTURES / "x1.gcx").write_text("-g py\n-a src/module\n", encoding="utf-8")
        dump = _run(["-x", "x1.gcx", "-x", "x1.gcx"])
        self.assertInDump("alpha.py", dump)  # executed without crashing

    def test_cli_overrides_x(self) -> None:
        (FIXTURES / "x2.gcx").write_text("-g js\n-a src/module\n", encoding="utf-8")
        dump = _run(["-x", "x2.gcx", "-g", "py"])
        self.assertInDump("alpha.py", dump)
        self.assertNotInDump("charlie.js", dump)

    def test_ai_in_subcontext_allowed(self) -> None:
        (FIXTURES / "ai.gcx").write_text(
            "-g py\n-a src/module/alpha.py\n--ai\n", encoding="utf-8"
        )
        with patch.object(ghconcat, "_call_openai") as mocked, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            _run(["-g", "py", "-a", "src/module/alpha.py", "-X", "ai.gcx"])
            mocked.assert_called_once()


class DefaultOutputDerivationTests(GhConcatBaseTest):
    def test_template_returns_rendered_output(self) -> None:
        tpl = FIXTURES / "dummy.tpl"
        tpl.write_text("{dump_data}", encoding="utf-8")
        dump = _run(["-g", "py", "-a", "src/module/alpha.py", "-t", str(tpl)])
        self.assertIn("def alpha()", dump)
        self.assertFalse((FIXTURES / "dummy.out.tpl").exists())


# --------------------------------------------------------------------------- #
#  Priority & disabling behaviours                                            #
# --------------------------------------------------------------------------- #
class PriorityAndNoneTests(GhConcatBaseTest):
    def test_cli_priority_over_multiple_x(self) -> None:
        """
        Two “‑x” files define different languages. A CLI “‑g py” must override
        both and include only Python files.
        """
        dump = _run(["-x", "xA.gcx", "-x", "xB.gcx", "-g", "py"])
        self.assertInDump("alpha.py", dump)
        self.assertNotInDump("charlie.js", dump)
        self.assertNotInDump("omega.xml", dump)

    def test_none_disables_parent_flag(self) -> None:
        """
        Parent “‑x” sets “‑n 5”. CLI overrides with “‑n none” so no truncation
        occurs (120 lines + header).
        """
        dump = _run(["-x", "disable_n.gcx", "-n", "none"])
        lines = dump.splitlines()
        body_lines = [l for l in lines if not l.startswith(HEADER_DELIM)]
        # full 120 lines from fixture
        self.assertEqual(len(body_lines), 120)


# --------------------------------------------------------------------------- #
#  Environment inheritance & overriding                                       #
# --------------------------------------------------------------------------- #
class EnvInheritanceTests(GhConcatBaseTest):
    def test_env_variable_expansion(self) -> None:
        """
        Parent defines “base=src”. Child dereferences $base and must resolve
        correctly.
        """
        dump = _run([
            "-g", "py",
            "-e", "base=src",
            "-X", "env_child.gcx",
        ])
        self.assertInDump("alpha.py", dump)

    def test_global_env_override(self) -> None:
        tpl = FIXTURES / "tpl_env.md"
        dump = _run([
            "-t", str(tpl),
            "-E", "project=Foo",
            "-X", "override_project.gcx",
        ])
        # template in child (--E project=Bar) must win
        self.assertIn("**Bar**", dump)
        self.assertNotIn("**Foo**", dump)


# --------------------------------------------------------------------------- #
#  Inline “[alias]” context creation                                          #
# --------------------------------------------------------------------------- #
class InlineContextAliasTests(GhConcatBaseTest):
    def test_inline_context_bracket_syntax(self) -> None:
        """
        The bracket syntax inside .gcx must behave like “‑X __ctx:alias”.
        """
        dump = _run(["-g", "js", "-X", "inline_parent.gcx"])
        self.assertInDump("charlie.js", dump)
        self.assertInDump("omega.xml", dump)  # comes from [mini]


# --------------------------------------------------------------------------- #
#  Wrap and header options                                                    #
# --------------------------------------------------------------------------- #
class WrapAndHeaderTests(GhConcatBaseTest):
    def test_wrap_with_P_no_header(self) -> None:
        dump = _run(["-g", "py", "-u", "python", "-P", "-a", "src/module/alpha.py"])
        # must start with fence, no header delimiter present
        self.assertTrue(dump.lstrip().startswith("```python"))
        self.assertNotIn(HEADER_DELIM, dump)


# --------------------------------------------------------------------------- #
#  Workspace resolution                                                       #
# --------------------------------------------------------------------------- #
class WorkspaceResolutionTests(GhConcatBaseTest):
    def test_W_relative_to_workdir(self) -> None:
        """
        Uses an alternate workspace containing a template.
        """
        alt_tpl = Path("ws_tpl/alt.tpl")
        dump = _run([
            "-g", "py",
            "-w", ".",  # default root
            "-W", "ws_tpl",  # workspace
            "-t", str(alt_tpl),
            "-a", "src/module/alpha.py",
        ])
        self.assertIn("ALT‑TPL", dump)


# --------------------------------------------------------------------------- #
#  AI seeds disabling                                                         #
# --------------------------------------------------------------------------- #
class AISeedsOptionTests(GhConcatBaseTest):
    def test_ai_seeds_none(self) -> None:
        """
        Passing “--ai-seeds none” must skip seed loading entirely.
        """
        tpl = FIXTURES / "ia_template.txt"

        def fake_call(prompt: str, out: Path, *_a, **_kw) -> None:  # noqa: D401
            out.write_text("AI‑OK", encoding="utf-8")

        with tempfile.TemporaryDirectory() as td, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}), \
                patch("ghconcat.src.ghconcat._call_openai", side_effect=fake_call) as mocked:
            out = Path(td) / "out.txt"
            _run([
                "-g", "py",
                "-O", "code",
                "-t", str(tpl),
                "--ai",
                "--ai-seeds", "none",
                "-o", str(out),
                "-a", "src/module/alpha.py",
            ])
            # Ensure seeds were NOT passed through kwargs
            self.assertTrue(mocked.called)
            _, kwargs = mocked.call_args
            self.assertIsNone(kwargs.get("seeds_path"))


class AbsolutePathHeaderTests(GhConcatBaseTest):
    def test_absolute_header_path(self) -> None:
        dump = _run([
            "-g", "py", "-p",  # absolute paths
            "-a", "src/module/alpha.py",
        ])
        self.assertRegex(dump, rf"{re.escape(str(FIXTURES))}.+alpha\.py")


class SuffixExcludeTests(GhConcatBaseTest):
    def test_S_excludes_suffix(self) -> None:
        dump = _run([
            "-g", "py",
            "-s", ".py",  # include .py
            "-S", ".testext",  # exclude .testext
            "-a", "src/module",
        ])
        self.assertNotInDump("file.testext", dump)


class NoneOverrideTests(GhConcatBaseTest):
    def test_template_disabled_with_none(self) -> None:
        tpl = FIXTURES / "base.tpl"
        dump = _run([
            "-t", str(tpl),
            "-t", "none",  # disable template
            "-g", "py",
            "-a", "src/module/alpha.py",
        ])
        # ya no contiene marcador de la plantilla
        self.assertNotIn("<!-- BASE -->", dump)

    def test_wrap_disabled_with_none(self) -> None:
        dump = _run([
            "-u", "python",
            "-u", "none",  # disable wrap
            "-g", "py",
            "-a", "src/module/alpha.py",
        ])
        self.assertNotIn("```python", dump)


class GlobalHeaderDedupTests(GhConcatBaseTest):
    def test_headers_deduplicated_without_template(self) -> None:
        dump = _run([
            "-g", "py",
            "-a", "src/module/alpha.py",
            "-X", "inline1.gcx", "-X", "inline2.gcx",
        ])
        # alpha.py aparece una sola cabecera
        self.assertEqual(dump.count("alpha.py"), 1)


class AliasAfterAITests(GhConcatBaseTest):
    def test_alias_points_to_ai_reply(self) -> None:
        tpl = FIXTURES / "ia_template.txt"

        def fake_call(prompt: str, out: Path, *_a, **_kw) -> None:
            out.write_text("AI‑FINAL", encoding="utf-8")

        with patch.object(ghconcat, "_call_openai", side_effect=fake_call), \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            dump = _run([
                "-g", "py",
                "-O", "code",
                "-t", str(tpl),
                "--ai",
                "-a", "src/module/alpha.py",
            ])
        self.assertIn("AI‑FINAL", dump)


# --------------------------------------------------------------------------- #
#  Entry‑point                                                                #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if DUMP.exists():
        try:
            DUMP.unlink()
        except OSError:
            shutil.rmtree(DUMP, ignore_errors=True)

    unittest.main(verbosity=2)
