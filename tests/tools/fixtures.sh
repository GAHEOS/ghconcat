#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# full_fixtures.sh – Builds the complete fixture tree for ghconcat test-suite
#
# • Combina la lógica de *fixtures.sh* y *fixtures_ext_directives.sh*.
# • Genera todos los archivos, directorios y workspaces adicionales.
#
# Usage
#   ./tests/tools/full_fixtures.sh               # => tests/test-fixtures
#   ./tests/tools/full_fixtures.sh /abs/path     # => /abs/path
#
# The script is idempotent: it wipes the target directory on each run.
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
  "$ROOT/src/other" \
  "$ROOT/extra/nested" \
  "$ROOT/build" \
  "$ROOT/.hidden" \
  "$ROOT/exclude_me"

# ---------- Base fixtures (original fixtures.sh) -------------------------------
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
--ia-set BATCH_DUMP
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
echo "console.log('space');" > "$ROOT/src/module/ünicode dir/file with space.js"

printf 'line1\r\nline2\r\n' > "$ROOT/extra/crlf.txt"

cat > "$ROOT/src/module/only_comments.py" <<'PY'
# nothing
# but
# comments
PY

echo "unknown ext" > "$ROOT/extra/sample.fooext"

cat > "$ROOT/batch_ws.gcx" <<'GCX'
-w /tmp
-a extra
-g .txt
--ia-set WS_BATCH
GCX

cat > "$ROOT/inline_wrap.gcx" <<'GCX'
-a "src/module/ünicode dir/file with space.js"
-g js
--ia-wrap js
GCX

mkdir -p "$ROOT/src/.private/inner"
echo "print('hidden nested')" > "$ROOT/src/.private/inner/nested.py"

# ---------- Extended directive fixtures (was fixtures_ext_directives.sh) -------
# Workspaces
mkdir -p "$ROOT/ws1/src/other" "$ROOT/ws2/src/module"
cp -a "$ROOT/src/other/."          "$ROOT/ws1/src/other/"
cp    "$ROOT/src/module/echo.dart" "$ROOT/ws2/src/module/"

# Inline -x files
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

# Batch -X files
cat > "$ROOT/batch1.gcx" <<'GCX'
-w ws1
-a src/other
-g py
-n 1
-N 3
GCX
cat > "$ROOT/batch2.gcx" <<'GCX'
-r src
-a other/delta.js
-g js
GCX
cat > "$ROOT/batch3.gcx" <<'GCX'
-w ws2
-r src
-a module/echo.dart
-g dart
GCX

echo "✅  Full fixture set READY"