# ghconcat

> **Concatenador jerárquico y agnóstico al lenguaje · ultra‑determinístico · cero dependencias externas**

`ghconcat` recorre tu árbol de proyecto, selecciona solo los archivos que te interesan, **elimina el ruido**
(comentarios, imports, líneas en blanco, etc.), aplica recortes opcionales por rango de líneas y concatena el resultado
en un único volcado reproducible.
Casos típicos:

* Prompts gigantes pero limpios para LLMs.
* Artefactos trazables en CI/CD.
* Paquetes para code‑review que conservan la estabilidad de números de línea.
* Una *fuente de verdad* que puedes incrustar en documentación o bases de conocimiento.

---

## 0 · TL;DR – Guía rápida

```bash
# 1 ─ Local + remoto: volcar .py + .xml **y .pdf** bajo addons/ y web/, ADEMÁS rastrear
#     https://gaheos.com dos niveles **Y** un único archivo desde GitHub,
#     envolver en Markdown y enviar a OpenAI:
ghconcat -s .py -s .xml -c -i -n 120 \
         -a addons -a web \
         https://github.com/GAHEOS/ghconcat^dev/src/ghconcat.py \
         https://gaheos.com --url-depth 2 \
         -u markdown \
         -s .pdf -y '/Confidential//g' \  # ← PDF incluido, limpia marcas de agua
         -t ai/prompt.tpl \
         -y '/secret//g' -Y '/secret_token/' # …reemplaza “secret” excepto el literal “secret_token”
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Dry‑run: listar cada HTML descubierto desde la página de inicio
ghconcat https://gaheos.com -s .html --url-depth 1 -l

# 3 ─ Pipeline declarativo multi‑paso con contextos
ghconcat -x conf/pipeline.gctx -o build/artifact.txt
```

---

## Table of Contents

1. [Filosofía](#1--filosofía)
2. [Compatibilidad ampliada de lenguajes y formatos de datos](#2--compatibilidad-ampliada-de-lenguajes-y-formatos-de-datos)
3. [Instalación](#3--instalación)
4. [Inicio rápido](#4--inicio-rápido)
5. [Referencia CLI](#5--referencia-cli)
6. [Modelo conceptual](#6--modelo-conceptual)
7. [Archivos de directivas y contextos](#7--archivos-de-directivas-y-contextos)
8. [Plantillas y variables](#8--plantillas-y-variables)
9. [Pasarela de IA](#9--pasarela-de-ia)
10. [Workspaces y salidas](#10--workspaces-y-salidas)
11. [Análisis avanzado (PDFs, URLs remotas y repos Git)](#11--análisis-avanzado-pdfs-urls-remotas-y-repos-git)

    * 11.1 [Ingesta de hojas de cálculo (.xls / .xlsx)](#111--ingesta-de-hojas-de-cálculo-xls--xlsx)
    * 11.2 [Obtención y rastreo de URLs (URLs + --url-depth)](#112--obtención-y-rastreo-de-urls-urls----url-depth)
    * 11.3 [Repositorios Git remotos (SPEC posicional)](#113--repositorios-git-remotos-spec-posicional)
    * 11.4 [Ingesta de PDF (.pdf)](#114--ingesta-de-pdf-pdf)
12. [Recetas](#12--recetas)
13. [Resolución de problemas](#13--resolución-de-problemas)
14. [Entorno y códigos de salida](#14--entorno-y-códigos-de-salida)
15. [Guía de contribución](#15--guía-de-contribución)
16. [Licencia](#16--licencia)

---

## 1 · Filosofía

| Principio                  | Razón                                                                                       |
|----------------------------|---------------------------------------------------------------------------------------------|
| **Determinismo primero**   | Mismos inputs ⇒ mismo volcado – perfecto para detectar drift en CI.                         |
| **Diseño componible**      | Mezcla one‑liners, archivos de directivas (`‑x`) y contextos jerárquicos en un solo script. |
| **Solo lectura & atómico** | Tus fuentes no se tocan; la salida se escribe solo donde indiques (`‑o`).                   |
| **Listo para LLM**         | Una sola bandera (`--ai`) conecta el volcado con OpenAI.                                    |
| **Cero dependencias**      | Python ≥ 3.8. El puente con OpenAI es opcional (`pip install openai`).                      |

---

## 2 · Compatibilidad ampliada de lenguajes y formatos de datos

El mapa de reglas de comentarios cubre **30+ lenguajes y formatos** populares, permitiendo depurar comentarios y
podar import/export con precisión a lo largo de una base moderna full‑stack.

| Extensión(es)         | Comentarios reconocidos   | Detección de imports      | Detección de exports      |
|-----------------------|---------------------------|---------------------------|---------------------------|
| `.py`                 | `# …` + docstrings        | `import / from`           | —                         |
| `.js`                 | `// …` y `/* … */`        | `import`                  | `export / module.exports` |
| `.ts` / `.tsx`        | idem JS                   | `import`                  | `export`                  |
| `.jsx`                | idem JS                   | `import`                  | `export`                  |
| `.dart`               | idem JS                   | `import`                  | `export`                  |
| `.go`                 | idem JS                   | `import`                  | —                         |
| `.rs`                 | idem JS                   | `use`                     | —                         |
| `.java`               | idem JS                   | `import`                  | —                         |
| `.kt` / `.kts`        | idem JS                   | `import`                  | —                         |
| `.swift`              | idem JS                   | `import`                  | —                         |
| `.c` / `.cpp` / `.cc` | idem JS                   | `#include`                | —                         |
| `.h` / `.hpp`         | idem C/C++                | `#include`                | —                         |
| `.cs`                 | idem JS                   | `using`                   | —                         |
| `.php`                | `//`, `#`, `/* … */`      | `require / include / use` | —                         |
| `.rb`                 | `# …`                     | `require`                 | —                         |
| `.sh` / `.bash`       | `# …`                     | `source / .`              | —                         |
| `.ps1`                | `# …`                     | `Import‑Module`           | —                         |
| `.lua`                | `-- …`                    | `require`                 | —                         |
| `.pl` / `.pm`         | `# …`                     | `use`                     | —                         |
| `.sql`                | `-- …`                    | —                         | —                         |
| `.html` / `.xml`      | `<!-- … -->`              | —                         | —                         |
| `.yml` / `.yaml`      | `# …`                     | —                         | —                         |
| `.css` / `.scss`      | `/* … */` y `// …` (SCSS) | —                         | —                         |
| `.r`                  | `# …`                     | `library()`               | —                         |
| `.xls`, `.xlsx`       | —                         | —                         | —                         |
| `.pdf`                | —                         | —                         | —                         |

---

## 3 · Instalación

### 3.1 Núcleo

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 -m pip install .
ghconcat --help
```

**Requisitos de ejecución**

* Python ≥ 3.8
* `argparse` y `logging` (stdlib)

### 3.2 Extras opcionales

| Funcionalidad                     | Paquetes / toolchain                                                   |
|-----------------------------------|------------------------------------------------------------------------|
| Puente OpenAI                     | `pip install openai`                                                   |
| Fetch/rastreo de URL\*            | `urllib` (stdlib)                                                      |
| Extracción de texto PDF (.pdf)    | `pip install pypdf`                                                    |
| OCR para PDFs escaneados          | `pip install pdf2image pytesseract`  + binarios de sistema **poppler** |
| Limpieza rápida y robusta de HTML | `pip install lxml`                                                     |
| Ingesta de Excel (.xls / .xlsx)   | `pip install pandas openpyxl` *o* `pandas xlrd` *o* `pandas pyxlsb`    |

\* Todo el networking usa la biblioteca estándar de Python.

---

## 4 · Inicio rápido

| Objetivo                               | Comando                                                                                  |
|----------------------------------------|------------------------------------------------------------------------------------------|
| Concatenar todos los **.py** de `src/` | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Auditoría limpia de un **add‑on Odoo** | `ghconcat -s .py -c -i -a addons/sale_extended`                                          |
| Listado en dry‑run                     | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Envolver y chatear con GPT             | `ghconcat -s .py -s .dart -c -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Pipeline de contextos                  | `ghconcat -x ci_pipeline.gctx -o build/ci_bundle.txt`                                    |

---

## 5 · Referencia CLI

| Categoría              | Bandera(s) (corta / larga)           | Propósito detallado                                                                                                                                                                                                                                                          |
|------------------------|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Ubicación**          | `-w DIR`, `--workdir DIR`            | Directorio raíz donde se descubren los archivos de contenido. Todas las rutas relativas en el contexto actual se resuelven desde aquí.                                                                                                                                       |
|                        | `-W DIR`, `--workspace DIR`          | Carpeta que almacena plantillas, prompts y salidas; por defecto es *workdir* si se omite.                                                                                                                                                                                    |
| **Descubrimiento**     | `-a PATH`, `--add-path PATH`         | Agrega un archivo **o** directorio (recursivo) al conjunto de inclusión. Repetible. *(Cualquier token sin prefijo `-` se convierte en `-a <token>`; las **URLs** y **especificaciones Git** se auto‑clasifican.)*                                                            |
|                        | `-A PATH`, `--exclude-path PATH`     | Excluye un árbol de directorios completo aunque haya sido incluido por un `-a` más amplio. Repetible.                                                                                                                                                                        |
|                        | `-s SUF`, `--suffix SUF`             | Lista blanca de extensiones (p. ej. `.py`). Con al menos un `-s`, el filtro se vuelve positivo (“permitir solo”). Repetible.                                                                                                                                                 |
|                        | `-S SUF`, `--exclude-suffix SUF`     | Lista negra de extensiones sin importar el origen (local o remoto). Repetible.                                                                                                                                                                                               |
|                        | `--url-depth N`                      | Profundidad para rastreo de URLs (por defecto **0**; `0` = solo fetch). Búsqueda en anchura hasta *N* desde cada semilla.                                                                                                                                                    |
|                        | `--url-allow-cross-domain`           | Levanta la restricción de mismo host durante el rastreo; se siguen dominios externos.                                                                                                                                                                                        |
|                        | `--url-policy module:Class`          | Política personalizada *UrlAcceptPolicy* para afinar qué enlaces se rastrean.                                                                                                                                                                                                |
| **Recorte por líneas** | `-n NUM`, `--total-lines NUM`        | Mantiene como máximo `NUM` líneas por archivo *después* de ajustar cabeceras.                                                                                                                                                                                                |
|                        | `-N LINE`, `--start-line LINE`       | Comienza la concatenación en la línea 1‑based `LINE` (puede combinarse con `-n`).                                                                                                                                                                                            |
|                        | `-m`, `--keep-first-line`            | Conserva siempre la primera línea original aunque el recorte empiece después.                                                                                                                                                                                                |
|                        | `-M`, `--no-first-line`              | Elimina la primera línea original, anulando un `-m` heredado.                                                                                                                                                                                                                |
| **Limpieza**           | `-c`, `--remove-comments`            | Elimina comentarios **(en línea y de línea completa)** y, cuando aplique, **docstrings** del lenguaje (p. ej. triple‑quoted de Python). Utiliza eliminadores con conciencia de lenguaje cuando están disponibles.                                                            |
|                        | `-C`, `--no-remove-comments`         | **Anula** la eliminación de comentarios/docstrings en el contexto actual (sobrescribe un `-c` heredado).                                                                                                                                                                     |
|                        | `-i`, `--remove-import`              | Elimina sentencias de importación donde aplique (`import`/`require`/`include`/`use`/`#include`).                                                                                                                                                                             |
|                        | `-I`, `--remove-export`              | Elimina declaraciones de exportación (JS/TS `export`, `module.exports`, …).                                                                                                                                                                                                  |
|                        | `-b`, `--strip-blank`                | Borra líneas en blanco remanentes tras la limpieza.                                                                                                                                                                                                                          |
|                        | `-B`, `--keep-blank`                 | Conserva líneas en blanco (anula un `-b` heredado).                                                                                                                                                                                                                          |
|                        | `-K`, `--textify-html`               | Convierte HTML/XHTML a texto plano antes de concatenar (elimina etiquetas).                                                                                                                                                                                                  |
| **Sustitución**        | `-y ESPEC`, `--replace ESPEC`        | Borra **(`/patrón/`)** o sustituye **(`/patrón/reemplazo/banderas`)** con regex estilo Python. Delimitador `/`; escapar como `\/`. Banderas: `g` (global), `i` (ignore‑case), `m` (multilínea), `s` (dot‑all). Patrones inválidos se registran y se ignoran silenciosamente. |
|                        | `-Y ESPEC`, `--preserve ESPEC`       | Protege regiones que coincidan con *ESPEC* de las reglas `-y` en el mismo contexto. Misma sintaxis/banderas que `-y`. Múltiples `-Y` definen varias máscaras de excepción.                                                                                                   |
| **Plantillas/salida**  | `-t FILE`, `--template FILE`         | Renderiza el volcado bruto con una plantilla minimalista. Los placeholders se expanden después.                                                                                                                                                                              |
|                        | `-T FILE`, `--child-template FILE`   | Establece una plantilla por defecto **solo para los contextos descendientes**. Los hijos pueden sobrescribir con su propio `-t` o sustituir con un nuevo `-T`.                                                                                                               |
|                        | `-o FILE`, `--output FILE`           | Escribe el resultado final a disco; la ruta se resuelve respecto al *workspace*.                                                                                                                                                                                             |
|                        | `-u LANG`, `--wrap LANG`             | Envuelve cada cuerpo de archivo en un bloque de código con fences, usando `LANG` como info‑string.                                                                                                                                                                           |
|                        | `-U`, `--no-wrap`                    | Cancela un `-u/--wrap` heredado en un contexto hijo.                                                                                                                                                                                                                         |
|                        | `-h`, `--header`                     | Emite cabeceras tipo banner (`===== path =====`) la primera vez que aparece cada archivo.                                                                                                                                                                                    |
|                        | `-H`, `--no-headers`                 | Suprime cabeceras en el contexto actual.                                                                                                                                                                                                                                     |
|                        | `-r`, `--relative-path`              | Muestra rutas de cabecera relativas a *workdir* (por defecto).                                                                                                                                                                                                               |
|                        | `-R`, `--absolute-path`              | Muestra rutas de cabecera absolutas.                                                                                                                                                                                                                                         |
|                        | `-l`, `--list`                       | *Modo listado*: imprime solo rutas de archivos descubiertos, una por línea.                                                                                                                                                                                                  |
|                        | `-L`, `--no-list`                    | Desactiva un modo listado heredado.                                                                                                                                                                                                                                          |
|                        | `-e VAR=VAL`, `--env VAR=VAL`        | Define una variable **local** visible solo en el contexto actual. Repetible.                                                                                                                                                                                                 |
|                        | `-E VAR=VAL`, `--global-env VAR=VAL` | Define una variable **global** heredada por contextos descendientes. Repetible.                                                                                                                                                                                              |
| **Control de STDOUT**  | `-O`, `--stdout`                     | Duplica siempre la salida final hacia STDOUT incluso si hay `-o`. Si `-o` falta en el contexto raíz, ya se transmite a STDOUT automáticamente.                                                                                                                               |
| **Puente IA**          | `--ai`                               | Envía el texto renderizado a OpenAI Chat; la respuesta se escribe en `-o` (o un archivo temporal) y se expone como `{_ia_ctx}` para plantillas.                                                                                                                              |
|                        | `--ai-model NAME`                    | Selección de modelo (por defecto **o3**).                                                                                                                                                                                                                                    |
|                        | `--ai-temperature F`                 | Temperatura de muestreo (modelos chat).                                                                                                                                                                                                                                      |
|                        | `--ai-top-p F`                       | Valor de *top‑p* (nucleus sampling).                                                                                                                                                                                                                                         |
|                        | `--ai-presence-penalty F`            | Parámetro de penalización por presencia.                                                                                                                                                                                                                                     |
|                        | `--ai-frequency-penalty F`           | Parámetro de penalización por frecuencia.                                                                                                                                                                                                                                    |
|                        | `--ai-system-prompt FILE`            | Archivo de *system prompt* (con placeholders).                                                                                                                                                                                                                               |
|                        | `--ai-seeds FILE`                    | Archivo JSONL con mensajes semilla para primar la conversación.                                                                                                                                                                                                              |
|                        | `--ai-max-tokens NUM`                | Máximo de tokens de salida (mapeo apropiado según API de Respuestas/Chat).                                                                                                                                                                                                   |
|                        | `--ai-reasoning-effort LEVEL`        | Esfuerzo de razonamiento para o‑series/gpt‑5: `low` \| `medium` \| `high`.                                                                                                                                                                                                   |
| **Lotes/contextos**    | `-x FILE`, `--directives FILE`       | Ejecuta un archivo de directivas con bloques `[context]`. Cada `-x` inicia un entorno aislado. Repetible.                                                                                                                                                                    |
| **Misceláneo**         | `--upgrade`                          | Auto‑actualiza *ghconcat* desde el repositorio oficial a `~/.bin`.                                                                                                                                                                                                           |
|                        | `--help`                             | Muestra la ayuda integrada y sale.                                                                                                                                                                                                                                           |
|                        | `--preserve-cache`                   | Conserva los directorios `.ghconcat_*cache` al finalizar.                                                                                                                                                                                                                    |
|                        | `--json-logs`                        | Emite logs en formato JSON en vez de texto plano.                                                                                                                                                                                                                            |
|                        | `--classifier REF`                   | Classifier personalizado como `module.path:ClassName` o `none`. También vía `GHCONCAT_CLASSIFIER`.                                                                                                                                                                           |
|                        | `--classifier-policies NAME`         | Conjunto de políticas para el classifier (`standard` \| `none`).                                                                                                                                                                                                             |

**Pistas**

* Un punto `·` tras una bandera en la lista original indica que la opción **es repetible** (todas las repetibles están
  explícitamente anotadas arriba).
* Cualquier token posicional que **no** empiece por `-` se expande automáticamente a `-a <token>`; las **URLs** y *
  *specs
  Git** se auto‑clasifican por el motor. Controla la recursión de URLs con `--url-depth`.
* Cualquier bandera que acepte valor puede neutralizarse en un contexto hijo pasando el literal `none` (p. ej.
  `-t none`).
* Todos los logs (INFO / ERROR) se emiten por **stderr**; redirige con `2>/dev/null` si necesitas un volcado limpio en
  STDOUT.
* Cuando `-y` y `-Y` aplican sobre el mismo texto, **ganan las reglas de preservación**: el segmento coincidente se
  restaura tras todas las sustituciones.

---

## 6 · Modelo conceptual

```
[a/include] → [A/exclude] → [s/S suffix] → limpieza → sustitución (-y/-Y) → recorte
                                          ↓
                       +──────── plantilla (‑t/‑T) ───+
                       |                              |
                       |        IA (--ai)             |
                       +───────────┬──────────────────+
                                   ↓
                               salida (‑o)
```

Las variables `‑e/-E` y los alias de contexto pueden interpolarse **en cualquier etapa posterior**.

---

## 7 · Archivos de directivas y contextos

### 7.1 Sintaxis

```gctx
# Valores globales
-w .
-s .py -s .yml
-b

[backend]
-a src/backend
-c -i

[frontend]
-a src/frontend
-u javascript
```

* Cada `[nombre]` inicia un **contexto hijo** que hereda banderas.
* Las banderas escalares sobrescriben; las de lista agregan; las booleanas se mantienen una vez activadas.
* No heredadas: `-o`, `-U`, `-L`, `--ai`.

### 7.2 Expansión automática de `‑a`

Dentro del archivo y en la CLI, cualquier token **que no comience con `‑`** se transforma en `‑a TOKEN`.
Esto te permite mezclar rutas y banderas de forma natural.

---

## 8 · Plantillas y variables

| Fuente de placeholder                 | Disponibilidad                              |
|---------------------------------------|---------------------------------------------|
| `{ctx}`                               | Salida final del contexto `ctx`             |
| `{_r_ctx}` / `{_t_ctx}` / `{_ia_ctx}` | Bruto / templateado / respuesta de IA       |
| `{ghconcat_dump}`                     | Concatenación de todos los contextos (raíz) |
| `$VAR`                                | Sustitución de entorno dentro de valores    |
| `‑e foo=BAR`                          | Variable local                              |
| `‑E foo=BAR`                          | Variable global                             |

En plantillas, escapa llaves con `{{`/`}}` para imprimir un `{}` literal.

---

## 9 · Pasarela de IA

| Aspecto            | Detalle                                                                                           |
|--------------------|---------------------------------------------------------------------------------------------------|
| Activación         | `--ai` y `OPENAI_API_KEY`                                                                         |
| Modelo por defecto | `o3`                                                                                              |
| Fuente del prompt  | Volcado renderizado + system prompt opcional (`--ai-system-prompt`) + semillas (`--ai-seeds`)     |
| Salida             | Se escribe en `‑o` (o archivo temporal) y se expone como `{_ia_ctx}`                              |
| Límites            | `--ai-max-tokens` limita la salida; `--ai-reasoning-effort` ajusta razonamiento en o‑series/gpt‑5 |
| Desactivar stub    | `GHCONCAT_DISABLE_AI=1` produce `"AI‑DISABLED"`                                                   |

---

## 10 · Workspaces y salidas

* `‑w` – dónde se descubren los archivos.
* `‑W` – dónde viven plantillas, prompts y salidas (por defecto `‑w`).
* Las rutas relativas se resuelven contra `‑w`/`‑W` del contexto actual.

---

## 11 · Análisis avanzado (PDFs, URLs remotas y repos Git)

### 11.1 · Ingesta de hojas de cálculo (.xls / .xlsx)

`ghconcat` puede leer libros de Microsoft Excel y convertir cada hoja en un volcado **TSV**:

* Cada hoja inicia con un banner
  `===== <sheet name> =====`
* Las celdas vacías se vuelven cadenas vacías para mantener la alineación.
* La función es **solo lectura**: el workbook original no se modifica.
* Dependencias: `pandas` **más** un motor de Excel (`openpyxl`, `xlrd` o `pyxlsb`).
  Si faltan, el archivo se omite en silencio y se registra una advertencia.

#### Ejemplo

```bash
# Concatenar todos los .xlsx bajo reports/ y eliminar líneas en blanco
ghconcat -s .xlsx -a reports -b -o tsv_bundle.txt
```

### 11.2 · Obtención y rastreo de URLs (URLs + --url-depth)

| Control                    | Comportamiento                                                                           |
|----------------------------|------------------------------------------------------------------------------------------|
| URLs semilla               | Añádelas como **tokens posicionales** (auto `-a`).                                       |
| `--url-depth N`            | Profundidad máxima BFS (por defecto `0`, `0` = sin enlaces – solo fetch).                |
| `--url-allow-cross-domain` | Sigue enlaces a otros dominios (desactivado por defecto).                                |
| Filtros de sufijo          | Se aplican **durante** el rastreo; solo se descargan recursos que coincidan.             |
| Logs                       | Mensajes `✔ fetched …` / `✔ scraped … (d=N)` por **stderr**. Silencia con `2>/dev/null`. |

#### Ejemplo

```bash
# Rastrear docs dos niveles y conservar solo .html y .pdf
ghconcat https://gaheos.com/docs --url-depth 2 -s .html -s .pdf -o web_bundle.txt
```

### 11.3 · Repositorios Git remotos (SPEC posicional)

| Formato SPEC             | Comportamiento                                                                                      |
|--------------------------|-----------------------------------------------------------------------------------------------------|
| `URL[^BRANCH][/SUBPATH]` | Clonado superficial en `.ghconcat_gitcache/` y adición de archivos que pasen los filtros de sufijo. |
| Limitar a subruta        | Añade `/SUBPATH` para restringir la ingesta.                                                        |
| Exclusiones              | Usa `-A` con rutas relativas (aplica tras la inclusión).                                            |

**Ejemplos**

```bash
# Repo completo, rama por defecto:
ghconcat https://github.com/pallets/flask.git -s .py

# Solo el directorio docs/ desde main:
ghconcat https://github.com/pallets/flask/docs -s .rst

# Un único archivo en rama dev:
ghconcat git@github.com:GAHEOS/ghconcat^dev/src/ghconcat.py -s .py
```

### 11.4 · Ingesta de PDF (`.pdf`)

`ghconcat` entiende **PDF** de forma nativa:

* Primero intenta extracción de texto embebido vía `pypdf`.
* Si el archivo no tiene texto *y* existen **pdf2image + pytesseract**, cae a OCR por página (300 dpi por defecto).
* Cada página se agrega en orden de lectura; las cabeceras muestran el nombre de archivo original.
* Funciona en forma transparente con limpieza, recorte y plantillas.

> **Consejo** Instala extras solo si necesitas OCR:
> `pip install pypdf pdf2image pytesseract`

```bash
# Concatenar todos los PDFs de docs/, eliminar líneas en blanco y envolver en fences markdown
ghconcat -s .pdf -a docs -b -u markdown -o manuals.md
```

---

## 12 · Recetas

<details>
<summary>12.1 Volcado apto para diff en code‑review</summary>

```bash
# rama main
ghconcat -s .py -c -i -a src -o /tmp/base.txt

# rama feature
ghconcat -s .py -c -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary>12.2 “Fuente de verdad” en Markdown</summary>

```bash
ghconcat -s .js -s .dart -c -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary>12.3 Pipeline de contextos con post‑proceso de IA</summary>

```gctx
[concat]
-w .
-a src
-s .py -c -i
-o concat.out.md

[humanize]
-a workspace/concat.out.md
-t tpl/humanize.md
--ai
-o human.out.md

[qa]
-W qa_workspace
-a workspace/human.out.md
-t tpl/qa_check.md
--ai
-o report.md
```

```bash
ghconcat -x pipeline.gctx
```

</details>

<details>
<summary>12.4 Paquete remoto + local</summary>

```bash
ghconcat -a src -s .py \
         https://gaheos.com/docs --url-depth 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

<details>
<summary>12.5 Síntesis académica a gran escala 📚🤖 (one‑shot `‑x`)</summary>

> Esta receta muestra cómo **un único archivo de directivas** orquesta un flujo de trabajo de investigación de extremo a
> extremo impulsado por múltiples “personas” LLM.
> Haremos:
>
> 1. Recolectar fuentes primarias desde notas locales **y** URLs abiertas.
> 2. Pedir a un *investigador junior* que elabore la primera síntesis.
> 3. Solicitar a un *investigador senior* que la refine.
> 4. Invitar a un *crítico académico* a desafiar las afirmaciones.
> 5. Aplicar un *editor de estilo* para claridad y concisión.
> 6. Llamar **otra vez** al crítico para una revisión final.
> 7. Guardar el informe pulido para que el equipo humano itere.

Todo el flujo está codificado en **`academic_pipeline.gctx`** (ver abajo).
Todos los artefactos intermedios viven en el *workspace*; cada etapa puede reutilizar la anterior ya sea mediante
`-a workspace/<file>` **o** referenciando el alias de contexto en una plantilla (`{junior}`, `{senior}`, …).

#### Ejecutar

```bash
ghconcat -x academic_pipeline.gctx -O
# El manuscrito final aparece en STDOUT y también se escribe en workspace/final_report.md
```

---

#### `academic_pipeline.gctx`

```text
// ======================================================================
//  ghconcat academic pipeline – Ejemplo de Computación Cuántica
//  Todo path que no empiece con “-” se interpreta como “-a <path>”.
// ======================================================================

# Ajustes globales -------------------------------------------------------
-w .                                   # raíz del proyecto con notes/
-W workspace                           # separar prompts + salidas
-E topic="Quantum Computing and Photonics"  # Visible en *todas* las plantillas

# -----------------------------------------------------------------------
# 0 · Recolectar corpus bruto  →  sources                               //
# -----------------------------------------------------------------------
[sources]
// Dos papers open‑access (render HTML)
https://arxiv.org/abs/2303.11366
https://arxiv.org/abs/2210.10255
--url-depth 0

-K                                      # limpiar (quitar etiquetas, scripts, etc.)
-s .html -c -i -u web-research -h       # limpiar y envolver
-o sources.md                           # expone {sources}

[notes]
-a notes/
-s .md -u note -h                       # envolver notas
-o notes.md                             # expone {notes}

# -----------------------------------------------------------------------
# 1 · Borrador del junior  →  junior                                    //
# -----------------------------------------------------------------------
[junior]
-a workspace/sources.md
-a workspace/notes.md
-t prompts/junior.md
--ai --ai-model o3
-o junior.out.md

# -----------------------------------------------------------------------
# 2 · Pasada del senior  →  senior                                      //
# -----------------------------------------------------------------------
[senior]
-a workspace/junior.out.md
-t prompts/senior.md
--ai
-o senior.out.md
-E to_critic=$senior

# -----------------------------------------------------------------------
# 3 · Primera crítica académica  →  critic1                             //
# -----------------------------------------------------------------------
[critic1]
-a workspace/senior.out.md
-t prompts/critic.md
--ai
-o critic1.out.md

# -----------------------------------------------------------------------
# 4 · Pulido de estilo y lenguaje  →  redraft                           //
# -----------------------------------------------------------------------
[redraft]
-a workspace/critic1.out.md
-t prompts/editor.md
--ai
-o redraft.out.md

# -----------------------------------------------------------------------
# 5 · Crítica final tras el pulido  →  critic2                          //
# -----------------------------------------------------------------------
[critic2]
-a workspace/redraft.out.md
-t prompts/critic.md
--ai
-o critic2.out.md
-E to_critic=$redraft

# -----------------------------------------------------------------------
# 6 · Paquete para humanos  →  final                                    //
# -----------------------------------------------------------------------
[final]
-a workspace/critic2.out.md
-h -R                                    # añadir banner con ruta absoluta
-o final_report.md
```

#### Archivos de prompt

> Guárdalos bajo `prompts/` (relativos al workspace).
> Cada plantilla puede acceder a:
>
> * `{topic}` – variable global definida con `‑E`.
> * `{sources}`, `{junior}`, `{senior}`, … – alias de contextos.

##### prompts/junior.md

````markdown
### Rol

Eres un **investigador/a junior** preparando una revisión inicial de literatura sobre **{topic}**.

### Tarea

1. Lee el corpus bruto ubicado en los bloques markdown ```note``` y ```web-research```.
2. Extrae **preguntas clave de investigación**, **metodologías** y **hallazgos principales**.
3. Devuelve un *esquema numerado* (máx. 1 000 palabras).

{notes}
{sources}
````

##### prompts/senior.md

```markdown
### Rol

Eres un/a **investigador/a senior** mentor/a de un colega junior.

### Tarea

Mejora el borrador:

* Fusionando puntos redundantes.
* Añadiendo trabajos seminales faltantes.
* Señalando debilidades metodológicas.

Devuelve un esquema revisado con comentarios inline donde aplicaste cambios.

### Antecedentes (web-research)

{sources}

### Notas del junior

{notes}

### Esquema del borrador

{junior}
```

##### prompts/critic.md

```markdown
### Rol

Formas parte de un *comité de revisión por pares ciega*.

### Tarea

1. Evalúa la coherencia lógica, soporte evidencial y afirmaciones de novedad.
2. Destaca **inexactitudes** o citas faltantes.
3. Califica cada sección (A–D) y justifica en ≤30 palabras.

Documento a revisar:

{to_critic}
```

##### prompts/editor.md

```markdown
### Rol

**Editor/a científico/a** profesional.

### Tarea

Reescribe para claridad, concisión y tono académico formal.  
Corrige pasiva excesiva, ajusta oraciones y asegura estilo IEEE.

## Resumen de la crítica

{critic1}

## Documento revisado

Fuente (revisado críticamente):
{senior}
```

##### notes/note\_lab\_log\_2025-06-03.md

```markdown
# Lab Log – 3 Jun 2025

*Guías de onda de nitruro de silicio integradas para entrelazamiento on‑chip*

## Objetivo

Probar el lote Si₃N₄ más reciente (run #Q-0601) para pérdidas, birrefringencia y visibilidad de interferencia de dos
fotones.

## Montaje

| Ítem          | Modelo                                | Notas            |
|---------------|----------------------------------------|------------------|
| Láser bomba   | TOPTICA iBeam-Smart 775 nm             | 10 mW CW         |
| Cristal PPLN  | Periodo = 7.5 µm                       | SPDC tipo‑0      |
| Montaje chip  | Temp. controlada (25 ± 0.01 °C)        | –                |
| Detectores    | Par SNSPD, η≈80 %                      | Jitter ≈ 35 ps   |

## Resultados clave

* Pérdida de propagación **1.3 dB ± 0.1 dB cm⁻¹** @ 1550 nm (cut‑back).
* Visibilidad HOM **91 %** sin filtrado espectral (mejor a la fecha).
* Sin birrefringencia apreciable dentro de ±0.05 nm de ajuste.

> **TODO**: simular dispersión para espirales de 3 cm; agendar ajustes de máscara e‑beam.
```

##### notes/note\_conference\_summary\_QIP2025.md

```markdown
# QIP 2025 – Resumen de sesión Hot‑topic

*Tokio, 27 Ene 2025*

## 1. Muestreo de bosones >100 fotones

**Ponente:** Jian-Wei Pan

* Límite de dureza 1 × 10⁻²₃ con interferómetro de 144 modos.
* Multiplexado en dominio temporal; reduce tamaño 40 ×.

## 2. Qubits fotónicos con corrección de errores

**Ponente:** Stefanie Barz

* Código **[[4,2,2]]** en qubits de doble rail con 97 % de fidelidad con heralding.
* Crecimiento de cluster‑state por puertas fusion‑II hasta 10⁶ time‑bins físicos.

## 3. Transducción NV‑centre ↔ fotón

**Ponente:** M. Atatüre

* Acoplo evanescente diamante‑SiN on‑chip, g≈30 MHz.
* Perspectiva: entrega determinista de estados Bell en >10 k enlaces.

### Tendencias transversales

* PPLN integrado y LiNbO₃ de película delgada **por doquier**.
* Migración de óptica bulk hacia plataformas heterogéneas III‑V + SiN.
* Mantra comunitario: **“mitigación de errores antes que corrección de errores”**.
```

##### notes/note\_review\_article\_highlights.md

```markdown
# Destacados – Review: *“Photonic Quantum Processors”* (Rev. Mod. Phys. 97, 015005 (2025))

| Sección               | Idea principal                                                                                      | Preguntas abiertas                                             |
|-----------------------|------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| Puertas LO            | CNOT determinista sigue exigiendo >90 dB de presupuesto; enfoques híbridos MBQC son los más promisorios. | ¿Con SNSPDs η_det ≥ 95 % + multiplexado temporal se cierra la brecha? |
| Fuentes integradas    | Micro‑anillos χ² on‑chip logran 300 MHz de tasa de pares a p‑pump = 40 mW.                           | ¿Escalado del crosstalk térmico más allá de 100 fuentes?       |
| Modelos de error      | La desfasación domina sobre pérdidas en guías estrechas.                                             | Se requiere *benchmarking* unificado entre *foundries*.        |
| Aplicaciones          | Ventaja a corto plazo en inferencia ML fotónica.                                                     | Trade‑off energía/latencia vs aceleradores AI en silicio.      |

### Crítica del autor

La review minimiza retos de criopackaging y el *costo real* del SiN ultra‑baja pérdida (≤0.5 dB m⁻¹). Incluir LCA
comparativa en trabajos futuros.
```

##### ¿Qué acaba de pasar?

| Etapa     | Entrada                   | Plantilla           | IA | Salida (alias)    |
|-----------|---------------------------|---------------------|----|-------------------|
| `sources` | Notas locales + dos ArXiv | — (concat cruda)    | ✗  | `{sources}`       |
| `junior`  | `sources.md` + `notes.md` | `junior.md`         | ✔  | `{junior}`        |
| `senior`  | `junior.md`               | `senior.md`         | ✔  | `{senior}`        |
| `critic1` | `senior.md`               | `critic.md`         | ✔  | `{critic1}`       |
| `redraft` | `critic1.md`              | `editor.md`         | ✔  | `{redraft}`       |
| `critic2` | `redraft.md`              | `critic.md`         | ✔  | `{critic2}`       |
| `final`   | `critic2.md` (sin IA)     | — (banner + concat) | ✗  | `final_report.md` |

El manuscrito final es **totalmente trazable**: se preservan todos los archivos intermedios, las cabeceras muestran
rutas
absolutas y puedes reproducir cualquier etapa re‑ejecutando su contexto con otras banderas o modelo.

¡Feliz investigación!

</details>

---

## 13 · Resolución de problemas

| Síntoma               | Sugerencia                                                                   |
|-----------------------|------------------------------------------------------------------------------|
| Volcado vacío         | Verifica rutas `‑a` y filtros de sufijos.                                    |
| Timeout de IA         | Revisa red, cuota o tamaño del prompt (> 128 k tokens?).                     |
| `{var}` sin resolver  | Define con `‑e`/`‑E` o asegúrate de que exista el alias de contexto.         |
| Cabeceras duplicadas  | No mezcles `‑h` y líneas de cabecera dentro de plantillas personalizadas.    |
| Imports persisten     | Usa `‑i` y/o `‑I` según el lenguaje.                                         |
| Demasiados ficheros   | Ajusta filtros `-s`/`-S` o reduce `--url-depth`.                             |
| Clone Git obsoleto    | Borra `.ghconcat_gitcache` o ejecuta sin `--preserve-cache`.                 |
| Replace no corrió     | Asegura que ESPEC esté **entre barras** (`/…/`) y no lo bloquee un `-Y`.     |
| Texto preservado mutó | Verifica que uses las *mismas banderas* (`g`, `i`, `m`, `s`) en `-y` y `-Y`. |

---

## 14 · Entorno y códigos de salida

| Variable                       | Propósito                                       |
|--------------------------------|-------------------------------------------------|
| `OPENAI_API_KEY`               | Habilita `--ai`.                                |
| `GHCONCAT_DISABLE_AI`          | `1` fuerza stub (sin red).                      |
| `GHCONCAT_JSON_LOGS`           | `1` habilita logs en formato JSON.              |
| `GHCONCAT_CLASSIFIER`          | Referencia de classifier (ver `--classifier`).  |
| `GHCONCAT_AI_REASONING_EFFORT` | Valor por defecto para `--ai-reasoning-effort`. |
| `DEBUG`                        | `1` imprime traceback de Python en errores.     |

| Código | Significado           |
|-------:|-----------------------|
|      0 | Éxito                 |
|      1 | Error fatal           |
|    130 | Interrumpido (Ctrl‑C) |

---

## 15 · Guía de contribución

* Estilo: `ruff` + `mypy --strict` + *black* por defecto.
* Tests: `python -m unittest -v` (o `pytest -q`).
* Formato de commit: `feat: add wrap‑U flag` (imperativo, sin punto final).
* Para refactors grandes abre un issue primero – ¡contribuciones bienvenidas!

---

## 16 · Licencia

Distribuido bajo **GNU Affero General Public License v3.0 o posterior (AGPL-3.0-or-later)**.

Copyright © 2025 GAHEOS S.A.
Copyright © 2025 Leonardo Gavidia Guerra

Consulta el archivo [`LICENSE`](./LICENSE) para el texto completo.

