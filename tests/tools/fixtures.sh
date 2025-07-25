#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# fixtures.sh – builds an exhaustive directory tree for ghconcat functional tests
# Usage: ./fixtures.sh [/absolute/path/for/fixtures]
# -----------------------------------------------------------------------------
set -euo pipefail

ROOT=${1:-"$(pwd)/test-fixtures"}     # destino por defecto

echo "Creating fixture tree in: $ROOT"
rm -rf "$ROOT"
mkdir -p \
  "$ROOT/src/module" \
  "$ROOT/src/other" \
  "$ROOT/extra/nested" \
  "$ROOT/build" \
  "$ROOT/.hidden" \
  "$ROOT/exclude_me"

# 1 · Python (con imports y comentarios simples)
cat > "$ROOT/src/module/alpha.py" <<'PY'
# simple comment
import os
from sys import argv  # inline

def alpha():
    """Return 1."""
    return 1  # trailing
PY

# 2 · Python sin comentarios
cat > "$ROOT/src/other/beta.py" <<'PY'
def beta():
    """Return 2."""
    return 2
PY

# 3 · JavaScript con import/export
cat > "$ROOT/src/module/charlie.js" <<'JS'
import { readFileSync } from 'fs';
// simple comment
export function charlie() {
  return 3; // inline
}
JS

# 4 · JavaScript sin comentarios
echo "export const delta = 4;" > "$ROOT/src/other/delta.js"

# 5 · XML
cat > "$ROOT/src/module/omega.xml" <<'XML'
<!-- xml comment -->
<root>
  <value>42</value>
</root>
XML

# 6 · CSV
echo -e "id,value\n1,foo\n2,bar" > "$ROOT/src/module/data.csv"

# 7 · Dart con import/export
cat > "$ROOT/src/module/echo.dart" <<'DART'
// simple
import 'dart:math';
export 'echo.dart'; // export
int echo() => 5;
DART

# 8 · Dart generado (debe ignorarse)
echo "// generated" > "$ROOT/build/ignore.g.dart"

# 9 · YML
cat > "$ROOT/src/module/config.yml" <<'YML'
# yml comment
key: value
YML

# 10 · YAML
cat > "$ROOT/extra/nested/config.yaml" <<'YAML'
another: value
YAML

# 11 · Go (extensión arbitraria)
cat > "$ROOT/extra/sample.go" <<'GO'
// simple comment
package main
func main() {}
GO

# 12 · TXT (para -k add‑ext)
echo "plain text" > "$ROOT/extra/notes.txt"

# 13 · Archivo oculto (debe ignorarse)
echo "# hidden" > "$ROOT/.hidden/secret.py"

# 14 · Archivo en directorio a excluir
echo "print('ignore me')" > "$ROOT/exclude_me/ignored.py"

# 15 · Large file para pruebas de rango (-n/-N)
seq 1 120 | sed 's/^/# line /' > "$ROOT/src/module/large.py"

# 16 · Prompt IA de ejemplo
cat > "$ROOT/ia_template.txt" <<'TPL'
### Context
{dump_data}

### Please summarise
TPL

# 17 · Archivo -x (inline flags)
cat > "$ROOT/inline.gcx" <<'GCX'
# sample inline directive
-a src/module
-g py
GCX

# 18 · Archivo -X (batch)
cat > "$ROOT/batch.gcx" <<'GCX'
-a extra
-g go
--ia-set BATCH_DUMP
GCX

# 19 · Archivo con sufijo especial
echo "suffix test" > "$ROOT/src/module/file.testext"

# 20 · Archivo con comentario complejo
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

# 23 · Archivo con espacios + unicode
mkdir -p "$ROOT/src/module/ünicode dir"
echo "console.log('space');" > "$ROOT/src/module/ünicode dir/file with space.js"

# 24 · TXT para -k add‑ext (prueba CRLF)
printf 'line1\r\nline2\r\n' > "$ROOT/extra/crlf.txt"

# 25 · Archivo solo comentarios
cat > "$ROOT/src/module/only_comments.py" <<'PY'
# nothing
# but
# comments
PY

# 26 · Extensión desconocida (fooext) para token --lang fooext
echo "unknown ext" > "$ROOT/extra/sample.fooext"

# 27 · Batch con workspace propio
cat > "$ROOT/batch_ws.gcx" <<'GCX'
-w /tmp
-a extra
-g .txt
--ia-set WS_BATCH
GCX

# 28 · Archivo inline -x con --ia-wrap
cat > "$ROOT/inline_wrap.gcx" <<'GCX'
-a "src/module/ünicode dir/file with space.js"
-g js
--ia-wrap js
GCX

# 29 · Ruta inexistente para prueba de warning
# (no se crea nada, solo referencia en tests)

# 30 · Directorio oculto anidado con archivo python
mkdir -p "$ROOT/src/.private/inner"
echo "print('hidden nested')" > "$ROOT/src/.private/inner/nested.py"

echo "Fixture set READY ✔"