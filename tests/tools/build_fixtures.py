#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_fixtures – Crea / refresca el árbol de *fixtures* empleado por la
test-suite de ghconcat (GAHEOS v2).

Idempotente y 100 % Python.
"""
from __future__ import annotations

import shutil
import stat
import textwrap
from pathlib import Path

ROOT = (Path(__file__).resolve().parents[2] / "test-fixtures").resolve()
FIX = ROOT  # alias usado por los tests

# ────────────────────────── utilidades ──────────────────────────
def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _chmod_x(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


# ───────────────────── archivos fuente ─────────────────────
def _populate_sources() -> None:
    src   = ROOT / "src/module"
    oth   = ROOT / "src/other"
    extra = ROOT / "extra/nested"
    excl  = ROOT / "exclude_me"

    _write(src / "alpha.py", """
        # simple comment
        import os
        def alpha():
            return 1  # trailing
    """)

    _write(src / "gamma.py", """
        # header line

        def gamma(x, y):
            return x + y


    """)

    _write(oth / "beta.py", """
        # blank line below

        def beta():
            return 2
    """)

    _write(src / "charlie.js", """
        // simple comment
        export const charlie = () => 3;
    """)

    _write(oth / "delta.js", "export const delta = 4;")
    _write(src / "omega.xml", "<root><v>42</v></root>")
    _write(src / "echo.dart", "int echo() => 5;")
    _write(src / "data.csv", "id,val\n1,a\n2,b")
    _write(src / "config.yml", "# yml\nkey: value")
    _write(extra / "config.yaml", "another: value")
    _write(ROOT / "extra/sample.go", "package main\nfunc main() {}")
    (ROOT / "extra/notes.txt").write_text("plain text\n", encoding="utf-8")

    (ROOT / ".hidden").mkdir(parents=True, exist_ok=True)
    _write(ROOT / ".hidden/secret.py", "# hidden")

    excl.mkdir(parents=True, exist_ok=True)
    _write(excl / "ignored.py", "print('ignored')")

    (ROOT / "extra/crlf.txt").write_bytes(b"line1\r\nline2\r\n")

    big = "\r\n".join(f"# line {i}" for i in range(1, 151))
    (src / "large.py").write_text(big, encoding="utf-8")

    uni = src / "ünicode dir"
    uni.mkdir(parents=True, exist_ok=True)
    _write(uni / "file with space.js", "console.log('unicode');")

    _write(src / "commented.js", "// c1\n/* block */\nexport const zeta = 6;")
    _write(src / "multi.yaml", "# one\n# two\nflag: true")
    _write(src / "file.testext", "ignored suffix")

    _write(ROOT / "ia_template.txt", """
        ### CONTEXT
        {ghconcat_dump}

        ### Summarise
    """)
    _write(ROOT / "ai/seeds.jsonl", '{"role":"user","content":"seed"}\n')

    for ws in ("ws1/src/other", "ws2/src/module"):
        (ROOT / ws).mkdir(parents=True, exist_ok=True)
    _copy(src / "echo.dart", ROOT / "ws2/src/module/echo.dart")
    for f in oth.iterdir():
        if f.is_file():
            _copy(f, ROOT / "ws1/src/other" / f.name)

    _write(ROOT / "base.tpl", "<!-- BASE -->\\n{ghconcat_dump}")
    _write(ROOT / "tpl_env.md", "**{project}**\\n{ghconcat_dump}")

    # ← U+2011 non-breaking hyphen entre “ALT” y “TPL”
    _write(ROOT / "ws_tpl/alt.tpl", "ALT─TPL\n{ghconcat_dump}")


# ───────────────── directivas .gctx ─────────────────
def _dir_inline(name: str, body: str) -> None:
    _write(ROOT / f"{name}.gctx", body)


def _generate_directives() -> None:
    _dir_inline("inline1", """
        [js]
        -h -s .js -a src/module/charlie.js
        -n 1 -N 2
    """)
    _dir_inline("inline2", """
        [xml]
        -h -s .xml -a src/module/omega.xml
        -n 2
    """)
    _dir_inline("blank_ctx", """
        -b -s .py

        [keep]
        -B
        -a src/module/gamma.py
    """)
    _dir_inline("ai_parent", """
        --ai-model gpt-4o

        [one]
        --ai
        -s .py -a src/module/alpha.py

        [two]
        -s .js -a src/module/charlie.js
    """)


# ──────────────────────────── main ────────────────────────────
def main() -> None:  # pragma: no cover
    if ROOT.exists():
        shutil.rmtree(ROOT)
    print(f"⚙️  Rebuilding fixture tree → {ROOT}")
    _populate_sources()
    _generate_directives()
    print("✅  Fixture tree READY")


if __name__ == "__main__":  # pragma: no cover
    main()