#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full functional test‑suite for *ghconcat* (spec v2, 2025‑07‑26).

All command‑line switches introduced in the refactor are exercised.  External
calls to OpenAI are mocked to keep the suite offline.
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
#  Dynamic import (works in editable installs and repo checkout)              #
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
#  Helpers and constants                                                      #
# --------------------------------------------------------------------------- #
FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / "test-fixtures"
DUMP = FIXTURES / "dump.txt"
WS1 = FIXTURES / "ws1"
WS2 = FIXTURES / "ws2"
INLINE_FILES = ["inline1.gcx", "inline2.gcx", "inline3.gcx"]
BATCH_FILES = ["batch1.gcx", "batch2.gcx", "batch3.gcx"]


@contextlib.contextmanager
def _inside_fixtures() -> Iterator[None]:
    """Temporarily ``chdir`` into the fixture root."""
    cwd = Path.cwd()
    os.chdir(FIXTURES)
    try:
        yield
    finally:
        os.chdir(cwd)


def _run(args: List[str]) -> str:
    """
    Execute *ghconcat* with *args*.

    • If the call already provides ``-w/--workspace`` or a top‑level ``-x``,
      we respect it; otherwise we inject ``-w FIXTURES`` for convenience.

    The working directory is always changed to *FIXTURES* so that relative
    paths inside gcx files resolve correctly.
    """
    base = list(args)
    has_workspace = any(a in ("-w", "--workspace") for a in base)
    if "-x" not in base and not has_workspace:
        base += ["-w", str(FIXTURES)]

    with _inside_fixtures():
        return GhConcat.run(base)


def _extract_segment(dump: str, filename: str) -> str:
    """
    Return the segment of *dump* corresponding to *filename*.

    Matches any path ending in *filename*, then captures until the next
    header delimiter or EOF.
    """
    pattern = re.compile(
        rf"{re.escape(HEADER_DELIM)}[^\n]*{re.escape(filename)}[^\n]*\n", re.M
    )
    m = pattern.search(dump)
    if not m:
        return ""
    start = m.end()
    nxt = dump.find(HEADER_DELIM, start)
    return dump[start:nxt if nxt != -1 else None]


# --------------------------------------------------------------------------- #
#  Directive‑fixture bootstrap (idempotent)                                   #
# --------------------------------------------------------------------------- #
def _ensure_directive_fixtures() -> None:
    """Create gcx files and workspaces on‑the‑fly (only if missing)."""
    if not WS1.exists():
        (WS1 / "src/other").mkdir(parents=True, exist_ok=True)
        for src in (FIXTURES / "src/other").iterdir():
            shutil.copy2(src, WS1 / "src/other" / src.name)
    if not WS2.exists():
        (WS2 / "src/module").mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            FIXTURES / "src/module/echo.dart",
            WS2 / "src/module/echo.dart",
        )
    directives = {
        "inline1.gcx": "-a src/module/charlie.js\n-g js\n-n 1\n-N 2\n",
        "inline2.gcx": "-a src/module/omega.xml\n-g xml\n-n 2\n",
        "inline3.gcx": "-a extra/sample.go\n-g go\n",
        "batch1.gcx": "-w ws1\n-a src/other\n-g py\n-n 1\n-N 3\n",
        "batch2.gcx": "-r src\n-a other/delta.js\n-g js\n",
        "batch3.gcx": "-w ws2\n-r src\n-a module/echo.dart\n-g dart\n",
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
    """Common helpers for all test cases."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES.exists():
            raise FixtureTreeMissing(
                "Fixture tree not found. Run tests/tools/fixtures.sh first."
            )

    # ---------- utilities ---------- #
    def assertInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertIn(member, dump, msg or f"'{member}' not found in dump")

    def assertNotInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertNotIn(member, dump, msg or f"'{member}' unexpectedly present in dump")


# --------------------------------------------------------------------------- #
#  Test‑suites                                                                #
# --------------------------------------------------------------------------- #
class BasicBehaviourTests(GhConcatBaseTest):
    """Standard happy‑path scenarios."""

    def test_basic_python_concat(self) -> None:
        """Default run with -g py must concatenate only *.py files."""
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
    """Comment, import and export removal flags."""

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
    """Line‑range slicing flags."""

    def test_range_n(self) -> None:
        dump = _run(["-g", "py", "-n", "10", "-a", "src/module/large.py"])
        self.assertEqual(dump.count("\n"), 11)  # header + 10 lines

    def test_range_nN_keep_header(self) -> None:
        dump = _run([
            "-g", "py", "-n", "50", "-N", "55", "-H",
            "-a", "src/module/large.py"
        ])
        lines = dump.splitlines()
        self.assertTrue(lines[1].startswith("# line 1"))
        numbered = [l for l in lines if l.startswith("# line ")]
        self.assertEqual(len(numbered), 51)  # 1 (header) + 50 sliced lines

    def test_range_N_only(self) -> None:
        """With only -N, dump must start exactly at that absolute line."""
        dump = _run(["-g", "py", "-N", "5", "-a", "src/module/large.py"])

        # Activa modo multilínea con (?m)
        self.assertRegex(dump, r"(?m)^# line 5$", "line 5 missing")
        self.assertNotRegex(dump, r"(?m)^# line 4$", "line 4 should be excluded")


class RouteAndBlankTests(GhConcatBaseTest):

    def test_route_only(self) -> None:
        dump = _run(["-g", "py", "-l", "-a", "src/module/alpha.py"])
        self.assertNotIn("def alpha", dump)

    def test_keep_blank(self) -> None:
        dump_no = _run(["-g", "py", "-a", "src/other/beta.py"])
        dump_yes = _run(["-g", "py", "-S", "-a", "src/other/beta.py"])
        self.assertGreater(len(dump_yes), len(dump_no))


class FilterTests(GhConcatBaseTest):

    def test_suffix_filter(self) -> None:
        dump = _run(["-g", "py", "-p", ".py", "-a", "src/module"])
        self.assertNotInDump("charlie.js", dump)
        self.assertInDump("alpha.py", dump)

    def test_additional_extension(self) -> None:
        dump = _run(["-g", "py", "-g", "go", "-a", "extra"])
        self.assertInDump("sample.go", dump)


class ExclusionTests(GhConcatBaseTest):

    def test_exclude_pattern(self) -> None:
        dump = _run(["-g", "py", "-a", ".", "-e", "ignored.py"])
        self.assertNotInDump("ignored.py", dump)

    def test_exclude_dir(self) -> None:
        dump = _run(["-g", "py", "-a", ".", "-E", "exclude_me"])
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

    def test_ai_template_and_wrap(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
                patch.object(ghconcat, "_call_openai") as dummy_call, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            out = Path(td) / "ia_output.txt"
            _run([
                "-g", "py",
                "--template", "ia_template.txt",
                "--ai",
                "-W", "python",
                "-o", str(out),
                "-a", "src/module/alpha.py"
            ])
            dummy_call.assert_called_once()
            prompt_sent = dummy_call.call_args.args[0]  # first positional arg
            self.assertIn("```python", prompt_sent)


class WorkspaceRootTests(GhConcatBaseTest):

    def test_workspace_and_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_ws:
            root = FIXTURES / "src"
            dump = GhConcat.run([
                "-g", "py",
                "-w", tmp_ws,
                "-r", str(root),
                "-a", "module/alpha.py"
            ])
            self.assertIn("alpha.py", dump)


class UpgradeFlagTests(GhConcatBaseTest):

    def test_upgrade_dry_run(self) -> None:
        called: list[bool] = []

        def fake_upgrade() -> None:  # noqa: D401
            called.append(True)
            raise SystemExit(0)

        import importlib
        pkg = importlib.import_module("ghconcat")  # top-level package

        with patch.object(pkg, "_perform_upgrade", fake_upgrade):
            with self.assertRaises(SystemExit):
                GhConcat.run(["--upgrade"])

        self.assertTrue(called and called[0])


class ExtraEdgeCaseTests(GhConcatBaseTest):
    """Additional corner‑cases."""

    def test_unknown_extension_inclusion(self) -> None:
        dump = _run(["-g", "fooext", "-a", "extra"])
        self.assertIn("sample.fooext", dump)

    def test_generated_dart_is_ignored(self) -> None:
        dump = _run(["-g", "dart", "-a", "build"])
        self.assertNotIn("ignore.g.dart", dump)

    def test_only_comments_file_is_skipped(self) -> None:
        dump = _run(["-g", "py", "-C", "-a", "src/module/only_comments.py"])
        self.assertNotIn("only_comments.py", dump)

    def test_route_only_keeps_header(self) -> None:
        dump = _run(["-g", "js", "-l", "-a", "src/module/charlie.js"])
        self.assertIn("===== ", dump)
        self.assertNotIn("export function", dump)

    def test_absolute_exclude_dir(self) -> None:
        abs_dir = FIXTURES / "exclude_me"
        dump = _run(["-g", "py", "-a", ".", "-E", str(abs_dir)])
        self.assertNotIn("ignored.py", dump)

    def test_skip_all_languages_fails(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-G", "py", "-a", "src"])


class CrossDirectiveCombinationTest(unittest.TestCase):
    """High‑coverage scenario combining 3×‑X batch + inline."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES.exists():
            raise RuntimeError("Fixture tree missing. Run full_fixtures.sh first.")
        _ensure_directive_fixtures()

    def test_multi_level_directives(self) -> None:
        """Validate combined output of 3 -X files (inline + batch)."""
        cli: List[str] = ["-g", "py", "-r", "."]
        # Inline directives are now processed via -X (level > 0)
        for xf in INLINE_FILES:
            cli += ["-X", xf]
        for bf in BATCH_FILES:
            cli += ["-X", bf]
        cli += ["-a", "src/module/alpha.py"]

        dump = _run(cli)

        expected = [
            "alpha.py",
            "charlie.js",
            "omega.xml",
            "sample.go",
            "beta.py",
            "delta.js",
            "echo.dart",
        ]
        for fname in expected:
            with self.subTest(file=fname):
                self.assertIn(fname, dump)

        # slicing charlie.js (inline1.gcx)
        charlie_seg = _extract_segment(dump, "charlie.js")
        self.assertIn("// simple comment", charlie_seg)
        self.assertNotIn("export function charlie", charlie_seg)

        # slicing omega.xml (inline2.gcx)
        omega_seg = _extract_segment(dump, "omega.xml")
        self.assertIn("<root>", omega_seg)
        self.assertNotIn("</root>", omega_seg)

        # slicing beta.py (batch1.gcx)
        beta_seg = _extract_segment(dump, "beta.py")
        self.assertIn("return 2", beta_seg)
        self.assertNotIn("def beta()", beta_seg)

        # header count = one per file
        header_count = dump.count(HEADER_DELIM)
        self.assertEqual(header_count, len(expected) * 2)


# --------------------------------------------------------------------------- #
#  NEW TESTS – extra coverage                                                 #
# --------------------------------------------------------------------------- #
class HeaderSemanticsTests(GhConcatBaseTest):
    def test_H_ignored_when_N1(self) -> None:
        dump = _run(["-g", "py", "-N", "1", "-H", "-a", "src/module/large.py"])
        self.assertEqual(dump.splitlines()[1], "# line 1")  # no duplicado

    def test_H_plus_N_and_n(self) -> None:
        dump = _run(["-g", "py", "-H", "-N", "40", "-n", "10",
                     "-a", "src/module/large.py"])
        lines = [l for l in dump.splitlines() if l.startswith("# line ")]
        self.assertEqual(lines[0], "# line 1")
        self.assertEqual(lines[1], "# line 40")
        self.assertEqual(len(lines), 11)  # 1 + 10


class AliasEnvTemplateTests(GhConcatBaseTest):
    def test_alias_and_env_interpolation(self) -> None:
        tpl = FIXTURES / "tpl.md"
        tpl.write_text("**{project}**\nPY:{py}\nGO:{go}\n", encoding="utf-8")
        (FIXTURES / "py.gcx").write_text("-a src/module/alpha.py\n-g py\n-A py\n",
                                         encoding="utf-8")
        (FIXTURES / "go.gcx").write_text("-a extra/sample.go\n-g go\n-A go\n",
                                         encoding="utf-8")

        dump = _run(["--template", str(tpl), "-V", "project=Demo",
                     "-X", "py.gcx", "-X", "go.gcx"])
        self.assertIn("**Demo**", dump)
        self.assertIn("def alpha()", dump)
        self.assertIn("package main", dump)

    def test_invalid_env_pair_fails(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-V", "malformed", "-a", "src/module/alpha.py"])


class WrapBehaviourTests(GhConcatBaseTest):
    def test_wrap_without_body(self) -> None:
        dump = _run(["-g", "js", "-l", "-W", "js",
                     "-a", "src/module/charlie.js"])
        self.assertNotIn("```", dump)

    def test_wrap_content(self) -> None:
        dump = _run(["-g", "js", "-W", "javascript",
                     "-a", "src/module/charlie.js"])
        self.assertIn("```javascript", dump)
        self.assertTrue(dump.strip().endswith("```"))


class ErrorScenarioTests(GhConcatBaseTest):
    def test_multiple_x_rejected(self) -> None:
        (FIXTURES / "x1.gcx").write_text("-g py\n-a src/module", encoding="utf-8")
        with self.assertRaises(SystemExit):
            _run(["-x", "x1.gcx", "-x", "x1.gcx"])

    def test_mixing_args_with_x_rejected(self) -> None:
        (FIXTURES / "x2.gcx").write_text("-g py\n-a src/module", encoding="utf-8")
        with self.assertRaises(SystemExit):
            _run(["-x", "x2.gcx", "-g", "py"])

    def test_forbidden_flag_in_X(self) -> None:
        (FIXTURES / "bad.gcx").write_text("-g py\n--ai\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-X", "bad.gcx"])

    def test_upgrade_with_extra_args_fails(self) -> None:
        with self.assertRaises(SystemExit):
            GhConcat.run(["--upgrade", "-g", "py"])


class DefaultOutputDerivationTests(GhConcatBaseTest):
    def test_template_sets_default_output_name(self) -> None:
        tpl = FIXTURES / "dummy.tpl"
        tpl.write_text("{dump_data}", encoding="utf-8")
        _run(["-g", "py", "-a", "src/module/alpha.py", "--template", str(tpl)])
        out = FIXTURES / "dummy.out.tpl"
        self.assertTrue(out.exists())


# --------------------------------------------------------------------------- #
#  Entry‑point                                                                #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Clean dump file between runs
    if DUMP.exists():
        try:
            DUMP.unlink()
        except OSError:
            shutil.rmtree(DUMP, ignore_errors=True)

    unittest.main(verbosity=2)
