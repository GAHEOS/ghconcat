#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full functional test-suite for *ghconcat.py* using the **unittest** framework.

It exercises every CLI switch (alone and in combination) with the fixture
tree built by *fixtures.sh* + *fixtures_extra.sh*.  External calls to OpenAI
are mocked to avoid network dependency.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest.mock import patch

# --------------------------------------------------------------------------- #
#  Adjust import path if ghconcat.py lives under ghconcat/src/ghconcat.py     #
# --------------------------------------------------------------------------- #
try:
    # Case 1 – installed or repo root
    import ghconcat  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import sys

    ROOT = Path(__file__).resolve().parents[2]  # adapt depth if needed
    sys.path.insert(0, str(ROOT / "ghconcat" / "src"))
    import ghconcat  # type: ignore

from ghconcat.src.ghconcat import GhConcat  # type: ignore

# --------------------------------------------------------------------------- #
#  Helpers and constants                                                      #
# --------------------------------------------------------------------------- #
FIXTURES = Path(__file__).resolve().parents[1] / 'tests' / "test-fixtures"
DUMP = FIXTURES / "dump.txt"  # default output file


def _run(args: List[str]) -> str:
    """Execute GhConcat with *args* forcing --workspace=FIXTURES."""
    return GhConcat.run(args + ["-w", str(FIXTURES)])


class FixtureTreeMissing(Exception):
    """Raised when the fixture tree was not generated."""


# --------------------------------------------------------------------------- #
#  Test case classes                                                          #
# --------------------------------------------------------------------------- #
class GhConcatBaseTest(unittest.TestCase):
    """Base class providing common helpers and pre-checks."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURES.exists():
            raise FixtureTreeMissing(
                "Fixture tree not found. Run ./fixtures.sh && ./fixtures_extra.sh"
            )

    # ---------- utilities ---------- #
    def assertInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertIn(member, dump, msg or f"'{member}' not found in dump")

    def assertNotInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertNotIn(member, dump, msg or f"'{member}' unexpectedly present in dump")


class BasicBehaviourTests(GhConcatBaseTest):
    """Standard happy-path scenarios."""

    def test_basic_python_concat(self) -> None:
        """Default run with -g py must concatenate only *.py files."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            dump = _run(["-g", "py", "-a", "src/module", "-f", str(out)])
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
    """Line-range slicing flags."""

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
        self.assertEqual(len(numbered), 6)


class RouteAndBlankTests(GhConcatBaseTest):

    def test_route_only(self) -> None:
        dump = _run(["-g", "py", "-t", "-a", "src/module/alpha.py"])
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

    def test_add_ext(self) -> None:
        dump = _run(["-g", "py", "-k", ".go", "-a", "extra"])
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


class IAIntegrationTests(GhConcatBaseTest):

    def test_ia_prompt_and_wrap(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
                patch("ghconcat.src.ghconcat._call_openai") as dummy_call, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            out = Path(td) / "ia_output.txt"
            _run([
                "-g", "py",
                "--ia-prompt", "ia_template.txt",
                "--ia-output", str(out),
                "--ia-wrap", "python",
                "-a", "src/module/alpha.py"
            ])
            dummy_call.assert_called_once()
            inp = FIXTURES / "ia_template.inputtxt"
            self.assertTrue(inp.exists())
            self.assertIn("```python", inp.read_text(encoding="utf-8"))


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

        with patch.object(ghconcat, "_perform_upgrade", fake_upgrade):
            with self.assertRaises(SystemExit):
                GhConcat.run(["-g", "py", "--upgrade"])
        self.assertTrue(called and called[0])


class ExtraEdgeCaseTests(unittest.TestCase):
    """Group of additional test‑cases that validate uncovered edge scenarios."""

    # ---------- PATH COVERAGE ---------- #
    def test_unknown_extension_inclusion(self) -> None:
        """A custom extension token (``fooext``) must activate ``.fooext`` files."""
        dump = _run(["--lang", "fooext", "-a", "extra"])
        self.assertIn("sample.fooext", dump)

    def test_generated_dart_is_ignored(self) -> None:
        """Files ending in ``.g.dart`` must never appear in the dump."""
        dump = _run(["-g", "dart", "-a", "build"])
        self.assertNotIn("ignore.g.dart", dump)

    def test_only_comments_file_is_skipped(self) -> None:
        """
        A file containing only comments must be fully skipped once all
        comments are removed with ``-C``.
        """
        dump = _run(["-g", "py", "-C", "-a", "src/module/only_comments.py"])
        # The header delimiter would reveal the file‑name; it must be absent.
        self.assertNotIn("only_comments.py", dump)

    # ---------- RANGE HANDLING ---------- #
    def test_range_N_only(self) -> None:
        """Providing only ``-N`` should return the first ``END‑1`` lines."""
        dump = _run(["-g", "py", "-N", "5", "-a", "src/module/large.py"])
        # Expect: header + 4 data lines ⇒ exactly 5 newline (splitlines len -1)
        self.assertEqual(dump.count("\n"), 5)

    # ---------- ROUTE / HEADER ---------- #
    def test_route_only_keeps_header(self) -> None:
        """When using ``-t`` ghconcat must output the header delimiter."""
        dump = _run(["-g", "js", "-t", "-a", "src/module/charlie.js"])
        self.assertIn("===== ", dump)  # header present
        self.assertNotIn("export function", dump)  # body absent

    # ---------- EXCLUSION LOGIC ---------- #
    def test_absolute_exclude_dir(self) -> None:
        """An absolute path passed to ``-E`` must exclude the directory."""
        abs_dir = FIXTURES / "exclude_me"
        dump = _run(["-g", "py", "-a", ".", "-E", str(abs_dir)])
        self.assertNotIn("ignored.py", dump)

    # ---------- ERROR CONDITIONS ---------- #
    def test_skip_all_languages_fails(self) -> None:
        """After applying ``--skip-lang`` ghconcat must abort when no ext remains."""
        with self.assertRaises(SystemExit):
            _run(["-g", "py", "-G", "py", "-a", "src"])


# --------------------------------------------------------------------------- #
#  Entry-point                                                               #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Ensure a clean dump file between runs
    if DUMP.exists():
        try:
            DUMP.unlink()
        except OSError:
            shutil.rmtree(DUMP, ignore_errors=True)

    unittest.main(verbosity=2)
