#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# fixtures.sh – Build the complete fixture tree for ghconcat test‑suite
# Spec v2, 2025‑08‑01  (extended)
# -----------------------------------------------------------------------------
set -euo pipefail

# ---------- Resolve destination ------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="${SCRIPT_DIR%/tests/tools*}/tests/test-fixtures"
ROOT="${1:-"$DEFAULT_ROOT"}"

echo "⚙️  Building fixture tree in: $ROOT"
rm -rf "$ROOT"
mkdir -p \
  "$ROOT/src/module" \
  "$ROOT/src/other"  \
  "$ROOT/extra/nested" \
  "$ROOT/build" \
  "$ROOT/.hidden" \
  "$ROOT/exclude_me" \
  "$ROOT/ai"

# ---------- Base fixtures ------------------------------------------------------
cat > "$ROOT/src/module/alpha.py" <<'PY'
# simple comment
import os
from sys import argv  # inline
def alpha():
    """Return 1."""
    return 1  # trailing
PY

cat > "$ROOT/src/other/beta.py" <<'PY'
def beta():
    """Return 2."""
    return 2
PY

cat > "$ROOT/src/module/charlie.js" <<'JS'
import { readFileSync } from 'fs';
// simple comment
export function charlie() {
  return 3; // inline
}
JS

echo "export const delta = 4;" > "$ROOT/src/other/delta.js"

cat > "$ROOT/src/module/omega.xml" <<'XML'
<!-- xml comment -->
<root>
  <value>42</value>
</root>
XML

echo -e "id,value\n1,foo\n2,bar" > "$ROOT/src/module/data.csv"

cat > "$ROOT/src/module/echo.dart" <<'DART'
// simple
import 'dart:math';
export 'echo.dart'; // export
int echo() => 5;
DART

echo "// generated" > "$ROOT/build/ignore.g.dart"

cat > "$ROOT/src/module/config.yml" <<'YML'
# yml comment
key: value
YML

cat > "$ROOT/extra/nested/config.yaml" <<'YAML'
another: value
YAML

cat > "$ROOT/extra/sample.go" <<'GO'
// simple comment
package main
func main() {}
GO

echo "plain text" > "$ROOT/extra/notes.txt"
echo "# hidden"   > "$ROOT/.hidden/secret.py"
echo "print('ignore me')" > "$ROOT/exclude_me/ignored.py"

seq 1 120 | sed 's/^/# line /' > "$ROOT/src/module/large.py"

cat > "$ROOT/ia_template.txt" <<'TPL'
### Context
{dump_data}

### Please summarise
TPL

cat > "$ROOT/inline.gcx" <<'GCX'
# sample inline directive
-a src/module
-g py
GCX

cat > "$ROOT/batch.gcx" <<'GCX'
-a extra
-g go
-O BATCH_DUMP
GCX

echo "suffix test" > "$ROOT/src/module/file.testext"

cat > "$ROOT/src/module/commented.js" <<'JS'
// simple
/* full comment block */
export const zeta = 6;
JS

cat > "$ROOT/src/module/multi.yaml" <<'YAML'
# first
#
# second
setting: true
YAML

mkdir -p "$ROOT/src/module/ünicode dir"
echo "console.log('space');" \
  > "$ROOT/src/module/ünicode dir/file with space.js"

printf 'line1\r\nline2\r\n' > "$ROOT/extra/crlf.txt"

cat > "$ROOT/src/module/only_comments.py" <<'PY'
# nothing
# but
# comments
PY


# ---------- Seeds for AI tests -------------------------------------------------
cat > "$ROOT/ai/seeds.jsonl" <<'JSONL'
{"role": "user", "content": "Seed 1"}
{"role": "assistant", "content": "Reply 1"}
JSONL

# ---------- Templates ----------------------------------------------------------
cat > "$ROOT/base.tpl" <<'TPL'
<!-- BASE -->
{dump_data}
TPL

cat > "$ROOT/child.tpl" <<'TPL'
<!-- CHILD -->
{dump_data}
TPL
cat > "$ROOT/tpl_env.md" <<'TPL'
**{project}**
{dump_data}
TPL
echo "unknown ext" > "$ROOT/extra/sample.fooext"

cat > "$ROOT/batch_ws.gcx" <<'GCX'
-w /tmp
-a extra
-g .txt
-k WS_BATCH
GCX

cat > "$ROOT/inline_wrap.gcx" <<'GCX'
-a "src/module/ünicode dir/file with space.js"
-g js
-a src/module
GCX

mkdir -p "$ROOT/src/.private/inner"
echo "print('hidden nested')" > "$ROOT/src/.private/inner/nested.py"
cat > "$ROOT/xA.gcx" <<'GCX'
-g js
-a src/module
GCX
cat > "$ROOT/xB.gcx" <<'GCX'
-g xml
-a src/module/omega.xml
GCX
cat > "$ROOT/disable_n.gcx" <<'GCX'
-n 5
-a src/module/large.py
GCX
cat > "$ROOT/env_child.gcx" <<'GCX'
-a $base/module/alpha.py
-O childdump
GCX
cat > "$ROOT/override_project.gcx" <<'GCX'
-E project=Bar
-t tpl_env.md
-a src/other/beta.py
GCX

# ---------- Inline‑context directive file using “[alias]” ----------------------
cat > "$ROOT/inline_parent.gcx" <<'GCX'
-a src/module/charlie.js
[mini]
-a src/module/omega.xml
-g xml
-O mini
GCX

# ---------- Workspaces for nested tests ---------------------------------------
mkdir -p "$ROOT/ws_tpl"
cat > "$ROOT/ws_tpl/alt.tpl" <<'TPL'
ALT‑TPL
{dump_data}
TPL

# ---------- Extended directive fixtures from original script ------------------
mkdir -p "$ROOT/ws1/src/other" "$ROOT/ws2/src/module"
cp -a "$ROOT/src/other/."          "$ROOT/ws1/src/other/"
cp    "$ROOT/src/module/echo.dart" "$ROOT/ws2/src/module/"

cat > "$ROOT/inline1.gcx" <<'GCX'
-a src/module/charlie.js
-g js
-n 1
-N 2
GCX
cat > "$ROOT/inline2.gcx" <<'GCX'
-a src/module/omega.xml
-g xml
-n 2
GCX
cat > "$ROOT/inline3.gcx" <<'GCX'
-a extra/sample.go
-g go
GCX
cat > "$ROOT/batch1.gcx" <<'GCX'
-w ws1
-a src/other
-g py
-n 1
-N 3
GCX
cat > "$ROOT/batch2.gcx" <<'GCX'
-a src
-a other/delta.js
-g js
GCX
cat > "$ROOT/batch3.gcx" <<'GCX'
-w ws2
-a src
-a module/echo.dart
-g dart
GCX

echo "✅  Full fixture set READY"