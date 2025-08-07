#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full functional test‑suite for *ghconcat* (spec v2 – 2025‑08‑05).

• Covers **100%** of public CLI flags + precedence rules.
• Exercises root‑level execution, multi‑context directive files, multi‑«‑x»
  sequences, environment inheritance, AI integration (offline mocks) and the
  self‑upgrade shortcut.
• No legacy flags «‑X/‑O» are used; everything follows GAHEOS v2 semantics.
"""
from __future__ import annotations

import contextlib
import os
import re
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Iterator, List
from unittest.mock import patch
import sys as _sys

# Dynamically ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1].parent
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

import ghconcat  # type: ignore  # noqa: E402

GhConcat = ghconcat.GhConcat  # type: ignore[attr-defined]
HEADER_DELIM = ghconcat.HEADER_DELIM  # type: ignore[attr-defined]

_sys.modules.setdefault("ghconcat", _sys.modules[__name__])
# --------------------------------------------------------------------------- #
#  Fixtures                                                                   #
# --------------------------------------------------------------------------- #
TOOLS_DIR = Path(__file__).resolve().parent / "tools"
FIXTURES = Path(__file__).resolve().parents[1] / "test-fixtures"
BUILD_SCRIPT = TOOLS_DIR / "build_fixtures.py"
os.environ["GHCONCAT_DISABLE_AI"] = "1"
# Build the tree once at import‑time — it is fast (< 0.2s)
subprocess.check_call([os.sys.executable, str(BUILD_SCRIPT)], stdout=subprocess.DEVNULL)


@contextlib.contextmanager
def _inside_fixtures() -> Iterator[None]:
    """Temporarily switch CWD to the fixture root."""
    cwd = Path.cwd()
    os.chdir(FIXTURES)
    try:
        yield
    finally:
        os.chdir(cwd)


# --------------------------------------------------------------------------- #
#  Helpers                                                                    #
# --------------------------------------------------------------------------- #
def _run(args: List[str]) -> str:
    """
    Execute *ghconcat* with *args* and return its final output string.

    If the caller does not provide ``-w/--workdir`` nor an «‑x» directive,
    this helper injects ``-w FIXTURES`` automatically.
    """
    base = list(args)
    if all(f not in ("-w", "--workdir") for f in base) and "-x" not in base:
        base += ["-w", str(FIXTURES)]

    with _inside_fixtures():
        return GhConcat.run(base)


def _extract_segment(dump: str, filename: str) -> str:
    """Return the chunk in *dump* that belongs to *filename* (header‑based)."""
    pat = re.compile(
        rf"{re.escape(HEADER_DELIM)}[^\n]*{re.escape(filename)}[^\n]*\n", re.M
    )
    m = pat.search(dump)
    if not m:
        return ""
    start = m.end()
    nxt = dump.find(HEADER_DELIM, start)
    return dump[start:nxt if nxt != -1 else None]


class Base(unittest.TestCase):
    def assertInDump(self, token: str, dump: str) -> None:
        self.assertIn(token, dump, f"'{token}' no encontrado")

    def assertNotInDump(self, token: str, dump: str) -> None:
        self.assertNotIn(token, dump, f"'{token}' apareció inesperadamente")


# --------------------------------------------------------------------------- #
#  Base class                                                                 #
# --------------------------------------------------------------------------- #
class GhConcatBaseTest(unittest.TestCase):
    """Utility mix‑in providing common assertions."""

    def assertInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertIn(member, dump, msg or f"'{member}' not found in dump")

    def assertNotInDump(self, member: str, dump: str, *, msg: str | None = None) -> None:
        self.assertNotIn(member, dump, msg or f"'{member}' unexpectedly present")


# --------------------------------------------------------------------------- #
#  1. Discovery & basic inclusion                                             #
# --------------------------------------------------------------------------- #
class DiscoveryTests(GhConcatBaseTest):
    def test_basic_py_concat(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.txt"
            dump = _run(["-h", "-s", ".py", "-a", "src/module", "-o", str(out)])
            self.assertInDump("alpha.py", dump)
            self.assertNotInDump("charlie.js", dump)
            self.assertTrue(out.exists())

    def test_suffix_in_both_S_and_s_is_kept(self) -> None:
        dump = _run(["-h", "-s", ".py", "-S", ".py", "-a", "src/module/alpha.py"])
        self.assertInDump("alpha.py", dump)

    def test_explicit_file_beats_exclusion(self) -> None:
        dump = _run([
            "-h",
            "-S", ".js",
            "-a", "src/module/charlie.js",  # explicit win
        ])
        self.assertInDump("charlie.js", dump)


# --------------------------------------------------------------------------- #
#  2. Cleaning flags                                                          #
# --------------------------------------------------------------------------- #
class CleaningTests(GhConcatBaseTest):
    def test_remove_simple_comments(self) -> None:
        dump = _run(["-s", ".py", "-c", "-a", "src/module/alpha.py"])
        self.assertNotIn("# simple comment", dump)

    def test_remove_all_comments(self) -> None:
        dump = _run(["-s", ".js", "-C", "-a", "src/module/commented.js"])
        self.assertNotIn("/* full", dump)

    def test_remove_imports(self) -> None:
        dump = _run(["-s", ".py", "-i", "-a", "src/module/alpha.py"])
        self.assertNotIn("import os", dump)

    def test_remove_exports(self) -> None:
        dump = _run(["-s", ".dart", "-I", "-a", "src/module/echo.dart"])
        self.assertNotIn("export", dump)


# --------------------------------------------------------------------------- #
#  3. Range slicing                                                           #
# --------------------------------------------------------------------------- #
class RangeTests(GhConcatBaseTest):
    def test_total_lines_n(self) -> None:
        dump = _run(["-h", "-s", ".py", "-n", "10", "-a", "src/module/large.py"])
        self.assertEqual(dump.count("\n"), 11)  # header + 10 lines

    def test_start_line_N_only(self) -> None:
        dump = _run(["-s", ".py", "-H", "-N", "5", "-a", "src/module/large.py"])
        self.assertRegex(dump, r"(?m)^# line 5$")
        self.assertNotRegex(dump, r"(?m)^# line 4$")

    def test_keep_first_line_m_vs_M(self) -> None:
        dump_keep = _run([
            "-s", ".py", "-m", "-n", "50", "-N", "55",
            "-a", "src/module/large.py",
        ])
        self.assertInDump("# line 1", dump_keep)

        dump_drop = _run([
            "-s", ".py", "-M", "-n", "50", "-N", "55",
            "-a", "src/module/large.py",
        ])
        self.assertNotInDump("# line 1", dump_drop)


# --------------------------------------------------------------------------- #
#  4. Header & blank‑line rules                                               #
# --------------------------------------------------------------------------- #
class HeaderBlankTests(GhConcatBaseTest):
    def test_header_default_hidden(self) -> None:
        dump = _run(["-s", ".py", "-a", "src/module/alpha.py"])
        self.assertNotIn(HEADER_DELIM, dump)

    def test_header_shown_with_h(self) -> None:
        dump = _run(["-h", "-s", ".py", "-a", "src/module/alpha.py"])
        self.assertIn(HEADER_DELIM, dump)

    def test_absolute_R_relative_r(self) -> None:
        dump_abs = _run(["-h", "-R", "-s", ".py", "-a", "src/module/alpha.py"])
        self.assertRegex(dump_abs, r"^===== /.+alpha\.py =====", msg="expected absolute path")

        dump_rel = _run(["-h", "-r", "-R", "-s", ".py", "-a", "src/module/alpha.py"])
        # both flags => default relative
        self.assertRegex(dump_rel, r"^===== src/module/alpha\.py =====", msg="expected relative path")

    def test_blank_strip_vs_keep(self) -> None:
        keep = _run(["-s", ".py", "-a", "src/other/beta.py"])
        strip = _run(["-s", ".py", "-b", "-a", "src/other/beta.py"])
        self.assertGreater(len(keep), len(strip))


# --------------------------------------------------------------------------- #
#  5. Inclusion / exclusion precedence                                        #
# --------------------------------------------------------------------------- #
class InclusionExclusionTests(GhConcatBaseTest):
    def test_exclude_directory(self) -> None:
        dump = _run(["-h", "-s", ".py", "-a", ".", "-A", "exclude_me"])
        self.assertNotInDump("ignored.py", dump)

    def test_exclude_suffix(self) -> None:
        dump = _run(["-h", "-s", ".py", "-S", ".testext", "-a", "src/module"])
        self.assertNotInDump("file.testext", dump)

    def test_hidden_files_skipped(self) -> None:
        dump = _run(["-h", "-s", ".py", "-a", "."])
        self.assertNotInDump("secret.py", dump)


# --------------------------------------------------------------------------- #
#  6. Template rendering & env interpolation                                  #
# --------------------------------------------------------------------------- #
class TemplateInterpolationTests(GhConcatBaseTest):
    def test_template_substitution_with_context_vars(self) -> None:
        tpl = FIXTURES / "base.tpl"
        _write = tpl.write_text
        _write("**{ctx_py}**\n{ctx_go}\n", encoding="utf-8")

        # Build a directive file with two contexts
        ctx_file = FIXTURES / "dual.gctx"
        ctx_file.write_text("""
            [ctx_py]
            -h
            -a src/module/alpha.py
            -s .py

            [ctx_go]
            -h
            -a extra/sample.go
            -s .go
        """, encoding="utf-8")

        dump = _run(["-x", str(ctx_file), "-t", str(tpl)])
        self.assertIn("def alpha", dump)
        self.assertIn("package main", dump)
        self.assertIn("**", dump)  # template ran

    def test_missing_env_variable_replaced_by_empty(self) -> None:
        tpl = FIXTURES / "empty.tpl"
        tpl.write_text("==>{missing}<==", encoding="utf-8")
        dump = _run(["-s", ".py", "-a", "src/module/alpha.py", "-t", str(tpl)])
        self.assertIn("==><==", dump)


# --------------------------------------------------------------------------- #
#  7. Wrap / unwrap behaviour                                                 #
# --------------------------------------------------------------------------- #
class WrapBehaviourTests(GhConcatBaseTest):
    def test_wrap_code_fence(self) -> None:
        dump = _run(["-s", ".js", "-u", "javascript", "-a", "src/module/charlie.js"])
        self.assertIn("```javascript", dump)
        self.assertTrue(dump.strip().endswith("```"))

    def test_wrap_cancelled_by_U(self) -> None:
        dump = _run([
            "-s", ".js", "-u", "javascript", "-U",
            "-a", "src/module/charlie.js",
        ])
        self.assertNotIn("```javascript", dump)


# --------------------------------------------------------------------------- #
#  8. Workspace resolution                                                    #
# --------------------------------------------------------------------------- #
class WorkspaceResolutionTests(GhConcatBaseTest):
    def test_W_relative_to_w(self) -> None:
        tpl = FIXTURES / "ws_tpl/alt.tpl"
        dump = _run([
            "-h",
            "-s", ".py",
            "-w", ".",
            "-W", "ws_tpl",
            "-t", str(tpl),
            "-a", "src/module/alpha.py",
        ])
        self.assertIn("ALT─TPL", dump)


# --------------------------------------------------------------------------- #
#  9. AI integration (offline)                                                #
# --------------------------------------------------------------------------- #
class AIIntegrationTests(GhConcatBaseTest):
    """All OpenAI calls are mocked."""

    def test_ai_reply_saved_and_alias_updated(self) -> None:
        tpl = FIXTURES / "ia_template.txt"

        def fake_call(prompt: str, out_path: Path, **_kw) -> None:
            out_path.write_text("AI‑FINAL", encoding="utf-8")

        with patch.object(ghconcat, "_call_openai", side_effect=fake_call) as mocked, \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            dump = _run([
                "-s", ".py",
                "-t", str(tpl),
                "--ai",
                "-a", "src/module/alpha.py",
            ])
            mocked.assert_called_once()
            self.assertIn("AI‑FINAL", dump)

    def test_ai_seeds_set_to_none(self) -> None:
        tpl = FIXTURES / "ia_template.txt"

        def fake_call(prompt: str, out_path: Path, **kwargs) -> None:
            self.assertIsNone(kwargs.get("seeds_path"))
            out_path.write_text("OK", encoding="utf-8")

        with patch.object(ghconcat, "_call_openai", side_effect=fake_call), \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            _run([
                "-s", ".py",
                "--ai",
                "--ai-seeds", "none",
                "-t", str(tpl),
                "-a", "src/module/alpha.py",
            ])


# --------------------------------------------------------------------------- #
# 10. Multi‑«‑x» execution & global dump                                      #
# --------------------------------------------------------------------------- #
class MultiXTests(GhConcatBaseTest):
    def test_multiple_x_independent(self) -> None:
        dump = _run(["-x", "inline1.gctx", "-x", "inline2.gctx"])
        self.assertInDump("charlie.js", dump)
        self.assertInDump("omega.xml", dump)

    def test_cli_flags_do_not_leak(self) -> None:
        # First ‑x sets ‑s .js, second ‑x inherits nothing
        ctx1 = FIXTURES / "x_js.gctx"
        ctx1.write_text("-s .js -a src/module -h", encoding="utf-8")
        ctx2 = FIXTURES / "x_py.gctx"
        ctx2.write_text("-s .py -a src/module -h", encoding="utf-8")

        dump = _run(["-x", str(ctx1), "-x", str(ctx2)])
        self.assertInDump("alpha.py", dump)
        self.assertInDump("charlie.js", dump)


# --------------------------------------------------------------------------- #
# 11. Error & edge cases                                                      #
# --------------------------------------------------------------------------- #
class ErrorEdgeCaseTests(GhConcatBaseTest):
    def test_none_disables_template(self) -> None:
        tpl = FIXTURES / "base.tpl"
        dump = _run([
            "-s", ".py",
            "-t", str(tpl),
            "-t", "none",
            "-a", "src/module/alpha.py",
        ])
        self.assertNotIn("<!-- BASE -->", dump)

    def test_upgrade_shortcut_invoked(self) -> None:
        called = False

        def fake_upgrade() -> None:  # noqa: D401
            nonlocal called
            called = True
            raise SystemExit(0)

        with patch.object(ghconcat, "_perform_upgrade", fake_upgrade):
            with self.assertRaises(SystemExit):
                GhConcat.run(["--upgrade"])
        self.assertTrue(called)

    def test_missing_template_fails(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["-s", ".py", "-t", "not_found.tpl", "-a", "src/module/alpha.py"])


# --------------------------------------------------------------------------- #
# 12. Global header de‑dup across contexts                                    #
# --------------------------------------------------------------------------- #
class HeaderDedupTests(GhConcatBaseTest):
    def test_single_header_for_duplicate_file(self) -> None:
        directive = FIXTURES / "dup.gctx"
        directive.write_text("""
            -h
            -s .py

            [one]
            -a src/module/alpha.py

            [two]
            -a src/module/alpha.py
        """, encoding="utf-8")

        dump = _run(["-x", str(directive)])
        self.assertEqual(dump.count("alpha.py"), 1)


# --------------------------------------------------------------------------- #
# 13. Jerarquía -b / -B                                                       #
# --------------------------------------------------------------------------- #
class BlankPrecedenceTests(Base):
    def test_parent_strip_child_keep(self) -> None:
        dump = _run(["-x", "blank_ctx.gctx", "-h"])
        # gamma.py contiene líneas en blanco: deben conservarse por el -B del contexto
        gamma_seg = re.search(r"gamma\.py[^\n]*\n(.+)", dump, re.S)
        self.assertIsNotNone(gamma_seg)
        self.assertRegex(gamma_seg.group(1), r"\n\s*\n", msg="líneas en blanco perdidas")


# --------------------------------------------------------------------------- #
# 14. Variable de entorno + template                                          #
# --------------------------------------------------------------------------- #
class EnvInterpolationTests(Base):
    def test_project_placeholder(self) -> None:
        tpl = FIXTURES / "tpl_env.md"
        dump = _run([
            "-s", ".py",
            "-a", "src/module/alpha.py",
            "-e", "project=GAHEOS",
            "-t", str(tpl),
        ])
        self.assertInDump("**GAHEOS**", dump)


# --------------------------------------------------------------------------- #
# 15. ghconcat_dump accesible en template root                                #
# --------------------------------------------------------------------------- #
class GlobalDumpTests(Base):
    def test_root_template_uses_global_dump(self) -> None:
        tpl = FIXTURES / "base.tpl"
        dump = _run([
            "-h",
            "-s", ".js",
            "-a", "src/module/charlie.js",
            "-t", str(tpl),
        ])
        self.assertInDump("charlie.js", dump)  # contenido
        self.assertInDump("<!-- BASE -->", dump)  # cabecera de plantilla


# --------------------------------------------------------------------------- #
# 16. Modo listado (-l)                                                       #
# --------------------------------------------------------------------------- #
class ListModeTests(Base):
    def test_list_only_paths(self) -> None:
        dump = _run(["-l", "-s", ".js", "-a", "src/module"])
        self.assertInDump("charlie.js", dump)
        self.assertNotInDump("export const charlie", dump)


# --------------------------------------------------------------------------- #
# 17. CR‑LF normalizado                                                       #
# --------------------------------------------------------------------------- #
class CRLFTests(Base):
    def test_crlf_file_read(self) -> None:
        dump = _run(["-s", ".txt", "-a", "extra/crlf.txt"])
        self.assertNotInDump("\r", dump)
        self.assertInDump("line2", dump)


# --------------------------------------------------------------------------- #
# 18. Encabezado con Unicode + espacios                                       #
# --------------------------------------------------------------------------- #
class UnicodePathTests(Base):
    def test_header_shows_unicode(self) -> None:
        dump = _run([
            "-h",
            "-s", ".js",
            "-a", "src/module/ünicode dir/file with space.js",
            "-o", "dump_q.txt",
        ])
        self.assertInDump("ünicode dir/file with space.js", dump)


# --------------------------------------------------------------------------- #
# 19. IA: flags heredados pero ejecución sólo si --ai                         #
# --------------------------------------------------------------------------- #
class AIInheritanceTests(Base):
    def test_only_one_ai_call(self) -> None:
        calls = 0

        def fake(prompt: str, out_path: Path, **_):
            nonlocal calls
            calls += 1
            out_path.write_text("AI‑OK", encoding="utf-8")

        with patch.object(ghconcat, "_call_openai", side_effect=fake), \
                patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            _run(["-x", "ai_parent.gctx"])
        self.assertEqual(calls, 1, "Se esperaba una única llamada IA")


# --------------------------------------------------------------------------- #
#  20. -L overrides -l                                                        #
# --------------------------------------------------------------------------- #
class ListOverrideTests(GhConcatBaseTest):
    """Verify that the new -L flag cancels the behaviour of -l."""

    def test_l_produces_listing(self) -> None:
        """Sanity-check the original -l behaviour."""
        dump = _run(["-l", "-s", ".py", "-a", "src/module/alpha.py"])
        self.assertEqual(
            dump.strip(),
            "src/module/alpha.py",
            "-l should output only the relative file path",
        )

    def test_L_cancels_l(self) -> None:
        """When both flags are present, -L wins and the file is concatenated."""
        dump = _run(["-l", "-L", "-s", ".py", "-a", "src/module/alpha.py"])
        self.assertInDump("def alpha", dump)  # file body present
        self.assertNotEqual(
            dump.strip(),
            "src/module/alpha.py",
            "-L must suppress the plain-listing output introduced by -l",
        )

    def test_L_alone_behaves_like_default(self) -> None:
        """Passing only -L should behave exactly as if no listing flags were used."""
        dump = _run(["-L", "-s", ".py", "-a", "src/module/alpha.py"])
        self.assertInDump("def alpha", dump)
        self.assertNotInDump("\nsrc/module/alpha.py\n", dump)  # no bare listing


# --------------------------------------------------------------------------- #
# 21. Environment-variable resolution & propagation                           #
# --------------------------------------------------------------------------- #
class EnvPropagationTests(GhConcatBaseTest):
    """
    Verify that «-e/-E» variables work inside the same «-x» unit and that
    only -E travels to nested contexts.
    """

    def test_local_env_used_same_context(self) -> None:
        d = FIXTURES / "env_same.gctx"
        d.write_text("""
            -e root=.
            -w $root
            -h
            -a src/module/alpha.py
            -s .py
        """, encoding="utf-8")
        dump = _run(["-x", str(d)])
        # Path appears, proving $root was expanded
        self.assertInDump("src/module/alpha.py", dump)

    def test_global_env_inherited(self) -> None:
        d = FIXTURES / "env_global.gctx"
        d.write_text("""
            -E root=src
            [child]
            -h
            -a $root/module/alpha.py
            -s .py
        """, encoding="utf-8")
        dump = _run(["-x", str(d)])
        # Child context receives $root
        self.assertInDump("src/module/alpha.py", dump)

    def test_local_env_not_inherited(self) -> None:
        d = FIXTURES / "env_local.gctx"
        d.write_text("""
            -e root=src
            [child]
            -h
            -a $root/module/alpha.py
            -s .py
        """, encoding="utf-8")
        dump = _run(["-x", str(d)])
        # Child did NOT inherit, so no alpha.py path makes it through
        self.assertNotInDump("alpha.py", dump)


# --------------------------------------------------------------------------- #
# 22. Remote URL fetching with -f/--url                                      #
# --------------------------------------------------------------------------- #

class RemoteURLTests(GhConcatBaseTest):
    """Validate the new -f/--url flag against a real HTML endpoint."""

    def test_fetch_url_contains_html(self) -> None:
        """
        Fetch https://www.gaheos.com with -f and confirm the dump includes the
        opening <html tag (case-insensitive).  Uses suffix filter to limit to
        .html content.
        """
        dump = _run(["-f", "https://www.gaheos.com", "-s", ".html", "-o", "dump_q.txt"])
        self.assertInDump("<html", dump.lower())


class ScrapeURLTests(GhConcatBaseTest):
    """Validate the -F/--url-scrape recursive crawler."""

    def test_html_scrape_recurses_and_keeps_html(self) -> None:
        """
        Crawl https://www.gaheos.com, restrict to .html, and ensure that:
        • The dump includes an <html tag (case-insensitive) from the root page.
        • More than one header banner appears, meaning at least two HTML
          resources were fetched (root + at least one linked page).
        """
        dump = _run(["-F", "https://www.gaheos.com", "-s", ".html", "-h", "-d", "1", "-o", "dump_q.txt"])
        self.assertInDump("<html", dump.lower())
        self.assertGreaterEqual(dump.count(HEADER_DELIM), 2,
                                "expected multiple HTML documents in scrape")

    def test_depth_zero_fetches_only_seed(self) -> None:
        """
        Depth 0 ⇒ solo la página raíz. Se valida contando headers.
        Suponemos que https://www.gaheos.com enlaza al menos a otra página
        interna (.html); con depth 0 no debe aparecer.
        """
        dump = _run([
            "-F", "https://www.gaheos.com",
            "-s", ".html",
            "-h",
            "-d", "0",  # profundidad cero
            "-o", "dump_q.txt",
        ])
        # Solo un encabezado esperado
        self.assertEqual(dump.count(HEADER_DELIM), 2,
                         "depth 0 should include only the seed URL")


# --------------------------------------------------------------------------- #
# 23. Interpolation - Escape “{{…}}”                                          #
# --------------------------------------------------------------------------- #
class InterpolationEscapeTests(unittest.TestCase):
    """Unit tests for the `{…}` / `{{…}}` interpolation semantics."""

    # Convenience alias to the function under test
    _interp = staticmethod(ghconcat._interpolate)

    def test_single_brace_is_interpolated(self) -> None:
        """{var} is replaced by its mapping value."""
        tpl = "Hello {user}"
        out = self._interp(tpl, {"user": "Leo"})
        self.assertEqual(out, "Hello Leo")

    def test_double_brace_is_preserved(self) -> None:
        """{{var}} is rendered as {var} without interpolation."""
        tpl = "Hello {{user}}"
        out = self._interp(tpl, {"user": "Leo"})
        self.assertEqual(out, "Hello {user}")

    def test_mixed_placeholders(self) -> None:
        """
        Interpolates single-brace placeholders while preserving
        double-brace literals in the same string.
        """
        tpl = "{{skip}} {user} {{name}} {missing}"
        out = self._interp(tpl, {"user": "Leo"})
        self.assertEqual(out, "{skip} Leo {name} ")

    def test_nested_like_sequences(self) -> None:
        """
        Edge-case: sequences such as '{{{var}}}' should result in '{Leo}'
        (outer '{{' is escape, inner '{var}' gets interpolated).
        """
        tpl = "{{{user}}}"
        out = self._interp(tpl, {"user": "Leo"})
        self.assertEqual(out, "{Leo}")

    def test_empty_mapping_replaces_with_empty_string(self) -> None:
        """Missing keys in mapping resolve to an empty string (legacy behaviour)."""
        tpl = "Status: {state}"
        out = self._interp(tpl, {})
        self.assertEqual(out, "Status: ")


# --------------------------------------------------------------------------- #
# 24. Interpolación con escape – integración completa                         #
# --------------------------------------------------------------------------- #
class InterpolationIntegrationTests(GhConcatBaseTest):
    """
    Verifica que la interpolación con llaves dobles funcione al ejecutar
    ghconcat desde la CLI, utilizando plantillas reales y variables de
    contexto/env.
    """

    def test_double_brace_literal_preserved(self) -> None:
        """
        Plantilla con {user} y {{user}}:
        • {user}  → se interpola usando -e user=Leo.
        • {{user}}→ se conserva y se emite como {user}.
        """
        tpl = FIXTURES / "tpl_escape1.tpl"
        tpl.write_text("Val: {user} & {{user}}", encoding="utf-8")

        dump = _run([
            "-s", ".py",
            "-a", "src/module/alpha.py",
            "-e", "user=Leo",
            "-t", str(tpl),
        ])

        self.assertInDump("Val: Leo & {user}", dump)

    def test_mixed_context_variables(self) -> None:
        """
        Usa un archivo .gctx con un contexto llamado [ctx]. La plantilla mezcla:
        • {{ctx}} – literal (no interpolar)  → debe renderizarse como {ctx}
        • {ctx}   – placeholder real          → debe contener el cuerpo de alpha.py
        """
        # 1. Plantilla
        tpl = FIXTURES / "tpl_escape2.tpl"
        tpl.write_text("**{{ctx}}** -> {ctx}", encoding="utf-8")

        # 2. Archivo de directivas con un contexto “ctx”
        gctx = FIXTURES / "single_ctx.gctx"
        gctx.write_text("""
            [ctx]
            -h
            -a src/module/alpha.py
            -s .py
        """, encoding="utf-8")

        # 3. Ejecutar ghconcat
        dump = _run(["-x", str(gctx), "-t", str(tpl)])

        # 4. Aserciones
        self.assertInDump("**{ctx}**", dump)  # literal preservado
        self.assertInDump("->", dump)  # flecha presente
        self.assertInDump("def alpha", dump)  # contenido interpolado


# --------------------------------------------------------------------------- #
# 25. Rutas posicionales en CLI                                               #
# --------------------------------------------------------------------------- #
class PositionalAddPathTests(GhConcatBaseTest):
    """
    Verifica que pasar archivos y directorios como argumentos posicionales en
    la CLI se comporte igual que usar «-a».
    """

    def test_cli_positional_paths_concatenate(self) -> None:
        """
        Ejecuta:
            ghconcat -h -s .py src/module/alpha.py src/other
        y comprueba que:
          • Se incluyan alpha.py y beta.py (dir src/other).
          • No aparezca charlie.js porque el filtro «-s .py» restringe a .py.
        """
        dump = _run([
            "-h",
            "-s", ".py",
            "src/module/alpha.py",  # archivo individual
            "src/other",  # directorio entero
        ])
        self.assertInDump("alpha.py", dump)
        self.assertInDump("beta.py", dump)
        self.assertNotInDump("charlie.js", dump)


# --------------------------------------------------------------------------- #
#  26. Salida estándar (-O / implícita sin -o)                                #
# --------------------------------------------------------------------------- #
class StdoutBehaviourTests(GhConcatBaseTest):
    """Comprueba la lógica de STDOUT introducida por -O."""

    # ---------- util ---------- #
    def _run_capture(self, args):
        """
        Ejecuta ghconcat capturando stdout.
        Devuelve (dump, stdout_str).
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dump = _run(args)
        return dump, buf.getvalue()

    # ---------- casos raíz ---------- #
    def test_auto_stdout_when_no_o(self) -> None:
        """Sin -o ⇒ volcado completo directo a STDOUT."""
        dump, stdout = self._run_capture(
            ["-s", ".py", "-a", "src/module/alpha.py"]
        )
        self.assertInDump("def alpha", stdout)
        # El dump retornado debe coincidir con lo impreso (salvo líneas de log)
        self.assertInDump("def alpha", dump)

    def test_no_stdout_with_only_o(self) -> None:
        """Con -o pero sin -O ⇒ nada del cuerpo en STDOUT (solo posible log)."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "file.txt"
            _, stdout = self._run_capture(
                ["-s", ".py", "-a", "src/module/alpha.py", "-o", str(out)]
            )
            self.assertTrue(out.exists())
            # No debe aparecer el código fuente
            self.assertNotInDump("def alpha", stdout)

    def test_stdout_duplication_with_O(self) -> None:
        """-o + -O duplica el resultado a STDOUT además del archivo."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "file.txt"
            dump, stdout = self._run_capture(
                ["-s", ".py", "-a", "src/module/alpha.py", "-o", str(out), "-O"]
            )
            self.assertTrue(out.exists())
            self.assertInDump("def alpha", stdout)
            # El cuerpo concatenado está incluido en la salida estándar
            self.assertInDump("def alpha", dump)

    # ---------- usos dentro de .gctx ---------- #
    def test_O_inside_context_with_o(self) -> None:
        """
        En un archivo de directivas:
        · Contexto con -o y -O ⇒ archivo + STDOUT para ese contexto.
        · Raíz sin -O ⇒ sin duplicación.
        """
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "ctx.txt"
            gctx = Path(td) / "sample.gctx"
            gctx.write_text(
                f"""
                -h
                -s .py

                [ctx]
                -a src/module/alpha.py
                -o {out_path}
                -O
                """,
                encoding="utf-8",
            )

            dump, stdout = self._run_capture(["-x", str(gctx)])
            self.assertTrue(out_path.exists(), "El archivo -o debía crearse")
            # Solo el contexto [ctx] debe reflejarse en STDOUT
            self.assertInDump("def alpha", stdout)
            # Aseguramos que el contenido se escribió también en el dump global
            self.assertInDump("def alpha", dump)


# --------------------------------------------------------------------------- #
# 23. Git‑repository inclusion (‑g / ‑G)                                      #
# --------------------------------------------------------------------------- #
class GitRepositoryTests(GhConcatBaseTest):
    """
    Functional tests for the new -g / -G flags.

    The tests clone the public «GAHEOS/ghconcat» repository inside the
    workspace’s ``.ghconcat_gitcache`` directory and verify:

    1. Full‑repository inclusion via -g.
    2. Exclusion of specific paths via -G.
    3. Sub‑path and branch handling.
    """

    REPO_URL = "https://github.com/GAHEOS/ghconcat"

    # ---------- helpers ---------- #
    @classmethod
    def setUpClass(cls):
        """
        Quickly check whether the remote repository is reachable.
        If the git command fails (e.g. no network) the whole class is skipped.
        """
        try:
            subprocess.check_call(
                ["git", "ls-remote", cls.REPO_URL],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("git network unavailable or repo down")

    # ---------- tests ---------- #
    def test_clone_and_include_all_py(self) -> None:
        """
        -g <repo> with «-s .py» must concatenate **all** Python files of the
        default branch, including the top‑level *ghconcat.py*.
        """
        dump = _run([
            "-h",
            "-s", ".py",
            "-g", self.REPO_URL,
        ])
        self.assertInDump("ghconcat.py", dump)
        self.assertGreaterEqual(dump.count(HEADER_DELIM), 3,
                                "expected several .py files from the repo")

    def test_exclude_specific_file_with_G(self) -> None:
        """
        «-G <repo>/ghconcat.py» must remove *only* that file, leaving the rest
        of the repository intact.
        """
        dump = _run([
            "-h",
            "-s", ".py",
            "-g", f'{self.REPO_URL}^dev',
            "-G", f"{self.REPO_URL}^dev/tests/test_ghconcat.py",
        ])
        self.assertNotInDump("test_ghconcat.py", dump)
        # Some other .py still present (e.g. tools/build_fixtures.py)
        self.assertRegex(dump, r"build_fixtures\.py", msg="other files should remain")

    def test_subpath_only(self) -> None:
        """
        Using a «/SUBPATH» suffix should restrict discovery to that subtree.
        """
        dump = _run([
            "-h",
            "-s", ".py",
            "-g", f"{self.REPO_URL}^dev/src/__init__.py",
        ])
        # Only the targeted file appears
        self.assertInDump("__init__.py", dump)
        self.assertEqual(dump.count(HEADER_DELIM), 2,
                         "only one header banner expected (one file)")

    def test_specific_branch(self) -> None:
        """
        If the repo exposes a «dev» branch, cloning with «^dev» must succeed.
        The test falls back to skipping if the branch does not exist.
        """
        branch = "main"
        try:
            subprocess.check_call(
                ["git", "ls-remote", "--exit-code", "--heads",
                 self.REPO_URL, branch],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except subprocess.CalledProcessError:
            self.skipTest(f"branch '{branch}' not found in upstream repo")

        dump = _run([
            "-h",
            "-s", ".py",
            "-g", f"{self.REPO_URL}^{branch}",
        ])
        self.assertInDump("ghconcat.py", dump)  # file in dev branch


# --------------------------------------------------------------------------- #
#  Utility for writing small template files                                   #
# --------------------------------------------------------------------------- #
def _write(path: Path, body: str, *, encoding: str = "utf-8") -> None:
    path.write_text(body, encoding=encoding)


# --------------------------------------------------------------------------- #
#  Entry‑point                                                                #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    unittest.main(verbosity=2)
