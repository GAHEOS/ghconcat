# ghconcat

> **Concatenador jerárquico, agnóstico al lenguaje · ultra‑determinista · cero dependencias externas**

`ghconcat` recorre el árbol de tu proyecto, selecciona solo los archivos que te interesan, **elimina el ruido**
(comentarios, imports, líneas en blanco, etc.), aplica un recorte opcional de rangos de líneas y concatena el resultado
en un único volcado reproducible.
Casos de uso típicos:

* Prompts gigantes pero limpios para LLMs.
* Artefactos trazables en CI/CD.
* Paquetes de revisión de código cuyos números de línea permanecen estables.
* Una *fuente de la verdad* que puedes incrustar en documentación o bases de conocimiento.

---

## 0 · TL;DR – Guía Rápida

```bash
# 1 ─ Local + remoto: volcar .py + .xml **y .pdf** bajo addons/ & web/, TAMBIÉN rastrear
#     https://gaheos.com dos niveles a profundidad **Y** un solo archivo de GitHub,
#     envolver en Markdown, enviar a OpenAI:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -g https://github.com/GAHEOS/ghconcat^dev/src/ghconcat.py \
         -F https://gaheos.com -d 2 \
         -u markdown \
         -s .pdf -y '/Confidential//g' \  # ← PDF incluido, limpia marcas de agua
         -t ai/prompt.tpl \
         -y '/secret//g' -Y '/secret_token/' # …reemplaza “secret” excepto “secret_token” literal
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Dry‑run: lista todo HTML descubierto accesible desde la página principal
ghconcat -F https://gaheos.com -s .html -l

# 3 ─ Pipeline declarativo de múltiples pasos con contextos
ghconcat -x conf/pipeline.gctx -o build/artifact.txt
```

---

## Tabla de Contenidos

1. [Filosofía](#1--filosofía)
2. [Compatibilidad Ampliada de Lenguajes y Formatos de Datos](#2--compatibilidad-ampliada-de-lenguajes-y-formatos-de-datos)
3. [Instalación](#3--instalación)
4. [Inicio Rápido](#4--inicio-rápido)
5. [Referencia CLI](#5--referencia-cli)
6. [Modelo Conceptual](#6--modelo-conceptual)
7. [Archivos de Directivas y Contextos](#7--archivos-de-directivas--contextos)
8. [Plantillas y Variables](#8--plantillas--variables)
9. [Pasarela IA](#9--pasarela-ia)
10. [Workspaces y Salidas](#10--workspaces--salidas)
11. [Análisis Avanzado (PDFs, URLs Remotas & Repos Git)](#11--análisis-avanzado-pdfs-urls-remotas--repos-git)

    * 11.1 [Ingesta de Hojas de Cálculo (.xls / .xlsx)](#111--ingesta-de-hojas-de-cálculo-xls--xlsx)
    * 11.2 [Rastreo y Scraping de URLs Remotas (`-f` / `-F`)](#112--repos-git-remotos--g---g)
    * 11.3 [Repositorios Git Remotos (`-g` / `-G`)](#113--ingesta-pdf-pdf)
12. [Recetas](#12--recetas)
13. [Resolución de Problemas](#13--resolución-de-problemas)
14. [Entorno y Códigos de Salida](#14--entorno--códigos-de-salida)
15. [Guía de Contribución](#15--guía-de-contribución)
16. [Licencia](#16--licencia)

---

## 1 · Filosofía

| Principio                  | Justificación                                                                              |
|----------------------------|--------------------------------------------------------------------------------------------|
| **Determinismo primero**   | Mismo input ⇒ volcado idéntico – perfecto para detectar drift en CI.                       |
| **Componible por diseño**  | Mezcla one‑liners, archivos de directiva (`‑x`) y contextos jerárquicos en un solo script. |
| **Solo lectura & atómico** | Tus fuentes nunca se tocan; la salida sólo se escribe donde la pidas (`‑o`).               |
| **Listo para LLM**         | Un solo flag (`--ai`) conecta el volcado con OpenAI.                                       |
| **Cero dependencias**      | Python ≥ 3.8 puro. El puente con OpenAI es opcional (`pip install openai`).                |

---

## 2 · Compatibilidad Ampliada de Lenguajes y Formatos de Datos

El mapa de reglas de comentarios cubre **más de 30 lenguajes y formatos de datos**, permitiendo eliminar con precisión
comentarios e imports/exports en un stack moderno full‑stack.

| Extensión(es)         | Comentarios reconocidos   | Detección de imports      | Detección de exports      |
|-----------------------|---------------------------|---------------------------|---------------------------|
| `.py`                 | `# …`                     | `import / from`           | —                         |
| `.js`                 | `// …` & `/* … */`        | `import`                  | `export / module.exports` |
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
| `.css` / `.scss`      | `/* … */` & `// …` (SCSS) | —                         | —                         |
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
mkdir -p ~/.bin && cp ghconcat.py ~/.bin/ghconcat && chmod +x ~/.bin/ghconcat
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat --help
```

**Requisitos de ejecución**

* Python ≥ 3.8
* `argparse` y `logging` (stdlib)

### 3.2 Extras opcionales

| Funcionalidad                   | Paquete(s) / toolchain                                                 |
|---------------------------------|------------------------------------------------------------------------|
| Puente OpenAI                   | `pip install openai`                                                   |
| Fetch/scrape de URL\*           | `urllib` (stdlib)                                                      |
| Extracción de texto PDF (.pdf)  | `pip install pypdf`                                                    |
| OCR para PDFs escaneados        | `pip install pdf2image pytesseract` + binarios **poppler** del sistema |
| Stripping HTML rápido y robusto | `pip install lxml`                                                     |
| Ingesta de Excel (.xls / .xlsx) | `pip install pandas openpyxl` *o* `pandas xlrd` *o* `pandas pyxlsb`    |

\* Todo el networking se basa en la librería estándar de Python.

---

## 4 · Inicio Rápido

| Objetivo                              | Comando                                                                                  |
|---------------------------------------|------------------------------------------------------------------------------------------|
| Concat. todos los **.py** bajo `src/` | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Auditoría de un **addon Odoo** limpio | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Listado en modo Dry‑run               | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Envolver & chatear con GPT            | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Pipeline de contextos                 | `ghconcat -x ci_pipeline.gctx -o build/ci_bundle.txt`                                    |

---

## 5 · Referencia CLI

| Categoría               | Flag(s) (corta / larga)                                       | Propósito detallado                                                                                                                                                                                                                                                                                |
|-------------------------|---------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Ubicación**           | `-w DIR`, `--workdir DIR`                                     | Directorio raíz donde se descubren los archivos de contenido. Todas las rutas relativas en el contexto actual se resuelven desde aquí.                                                                                                                                                             |
|                         | `-W DIR`, `--workspace DIR`                                   | Carpeta que almacena plantillas, prompts y salidas; por defecto es *workdir* si se omite.                                                                                                                                                                                                          |
| **Descubrimiento**      | `-a PATH`, `--add-path PATH`                                  | Añade un archivo **o** directorio (recursivo) al conjunto de inclusión. Repetible.                                                                                                                                                                                                                 |
|                         | `-A PATH`, `--exclude-path PATH`                              | Excluye un directorio completo incluso si fue añadido por un `-a` más amplio. Repetible.                                                                                                                                                                                                           |
|                         | `-s SUF`, `--suffix SUF`                                      | Lista blanca de extensión(es) (ej. `.py`). Al menos un `-s` convierte el filtro en “solo permitir”. Repetible.                                                                                                                                                                                     |
|                         | `-S SUF`, `--exclude-suffix SUF`                              | Lista negra de extensiones sin importar su origen (local o remoto). Repetible.                                                                                                                                                                                                                     |
|                         | `-f URL`, `--url URL`                                         | *Fetch* de un único recurso remoto y cacheo como archivo local (nombre preservado o inferido). Repetible.                                                                                                                                                                                          |
|                         | `-F URL`, `--url-scrape URL`                                  | Crawler con profundidad limitada partiendo de cada URL semilla; descarga todo recurso enlazado que pase los filtros de sufijo/exclusión activos. Repetible.                                                                                                                                        |
|                         | `-g SPEC`, `--git-path SPEC` `SPEC = URL[^BRANCH][/SUBPATH]`. | **Incluye fuentes de un repo *Git* remoto**. Si se omite *BRANCH*, se usa la rama por defecto; si se omite *SUBPATH* se escanea todo el repo.                                                                                                                                                      |
|                         | `-G SPEC`, `--git-exclude SPEC`                               | Excluye un archivo o subárbol dentro de un repo previamente añadido con `-g`.                                                                                                                                                                                                                      |
|                         | `-d N`, `--url-scrape-depth N`                                | Profundidad máxima para `-F` (por defecto **2**; `0` = solo página semilla).                                                                                                                                                                                                                       |
|                         | `-D`, `--disable-same-domain`                                 | Levanta la restricción de mismo dominio al hacer scraping; se siguen dominios externos.                                                                                                                                                                                                            |
| **Corte de líneas**     | `-n NUM`, `--total-lines NUM`                                 | Mantiene como máximo `NUM` líneas por archivo *después* del ajuste de cabecera.                                                                                                                                                                                                                    |
|                         | `-N LINE`, `--start-line LINE`                                | Empieza la concatenación en la línea `LINE` (1‑based) (se puede combinar con `-n`).                                                                                                                                                                                                                |
|                         | `-m`, `--keep-first-line`                                     | Conserva siempre la primera línea original incluso si el corte empieza después.                                                                                                                                                                                                                    |
|                         | `-M`, `--no-first-line`                                       | Fuerza eliminación de la primera línea original, sobrescribiendo un `-m` heredado.                                                                                                                                                                                                                 |
| **Limpieza**            | `-c`, `--remove-comments`                                     | Elimina solo comentarios *inline* (con conciencia de lenguaje).                                                                                                                                                                                                                                    |
|                         | `-C`, `--remove-all-comments`                                 | Elimina comentarios inline **y** de línea completa.                                                                                                                                                                                                                                                |
|                         | `-i`, `--remove-import`                                       | Elimina sentencias `import` / `require` / `use` (Python, JS, Dart, …).                                                                                                                                                                                                                             |
|                         | `-I`, `--remove-export`                                       | Elimina declaraciones `export` / `module.exports` (JS, TS, …).                                                                                                                                                                                                                                     |
|                         | `-b`, `--strip-blank`                                         | Borra líneas en blanco que queden tras la limpieza.                                                                                                                                                                                                                                                |
|                         | `-B`, `--keep-blank`                                          | Preserva líneas en blanco (anula un `-b` heredado).                                                                                                                                                                                                                                                |
| **Sustitución**         | `-y SPEC`, `--replace SPEC`                                   | Borra **(`/patrón/`)** o reemplaza **(`/patrón/repl/flags`)** fragmentos que hacen match con la regex estilo Python *patrón*. Delimitador “/”; escápalo como `\/`. Flags: `g` (global), `i` (ignore‑case), `m` (multiline), `s` (dot‑all). Patrones inválidos se ignoran silenciosamente tras log. |
|                         | `-Y SPEC`, `--preserve SPEC`                                  | Protege regiones que hagan match con *SPEC* de reglas `-y` en el mismo contexto. Sintaxis, escape y flags idénticos a `-y`. Se pueden usar múltiples `-Y`.                                                                                                                                         |
| **Plantillas & salida** | `-t FILE`, `--template FILE`                                  | Renderiza el dump crudo a través de una plantilla Jinja‑lite. Los placeholders se expanden después.                                                                                                                                                                                                |
|                         | `-o FILE`, `--output FILE`                                    | Escribe el resultado final en disco; la ruta se resuelve contra *workspace*.                                                                                                                                                                                                                       |
|                         | `-u LANG`, `--wrap LANG`                                      | Envuelve cada cuerpo de archivo en un bloque de código con `LANG` como info‑string.                                                                                                                                                                                                                |
|                         | `-U`, `--no-wrap`                                             | Cancela un wrap heredado en un contexto hijo.                                                                                                                                                                                                                                                      |
|                         | `-h`, `--header`                                              | Emite cabeceras grandes (`===== path =====`) la primera vez que aparece cada archivo.                                                                                                                                                                                                              |
|                         | `-H`, `--no-headers`                                          | Suprime cabeceras en el contexto actual.                                                                                                                                                                                                                                                           |
|                         | `-r`, `--relative-path`                                       | Muestra rutas de cabecera relativas a *workdir* (por defecto).                                                                                                                                                                                                                                     |
|                         | `-R`, `--absolute-path`                                       | Muestra rutas de cabecera absolutas.                                                                                                                                                                                                                                                               |
|                         | `-l`, `--list`                                                | *Modo lista*: imprime solo las rutas de archivos descubiertos, una por línea.                                                                                                                                                                                                                      |
|                         | `-L`, `--no-list`                                             | Deshabilita un modo lista heredado.                                                                                                                                                                                                                                                                |
|                         | `-e VAR=VAL`, `--env VAR=VAL`                                 | Define una variable **local** visible solo en el contexto actual. Repetible.                                                                                                                                                                                                                       |
|                         | `-E VAR=VAL`, `--global-env VAR=VAL`                          | Define una variable **global** heredada por contextos descendientes. Repetible.                                                                                                                                                                                                                    |
| **Control STDOUT**      | `-O`, `--stdout`                                              | Duplica siempre la salida final a STDOUT, incluso cuando existe `-o`. Si falta `-o` en la raíz, ya se hace streaming a STDOUT.                                                                                                                                                                     |
| **Puente IA**           | `--ai`                                                        | Envía el texto renderizado a OpenAI Chat; la respuesta se escribe en `-o` (o temp) y se expone como `{_ia_ctx}` para plantillas.                                                                                                                                                                   |
|                         | `--ai-model NAME`                                             | Selecciona modelo de chat (por defecto **o3**).                                                                                                                                                                                                                                                    |
|                         | `--ai-temperature F`                                          | Temperatura de muestreo (ignorado para *o3*).                                                                                                                                                                                                                                                      |
|                         | `--ai-top-p F`                                                | Valor top‑p (nucleus sampling).                                                                                                                                                                                                                                                                    |
|                         | `--ai-presence-penalty F`                                     | Parámetro presence‑penalty.                                                                                                                                                                                                                                                                        |
|                         | `--ai-frequency-penalty F`                                    | Parámetro frequency‑penalty.                                                                                                                                                                                                                                                                       |
|                         | `--ai-system-prompt FILE`                                     | Archivo de prompt de sistema (placeholder‑aware).                                                                                                                                                                                                                                                  |
|                         | `--ai-seeds FILE`                                             | Mensajes seed JSONL para primar el chat.                                                                                                                                                                                                                                                           |
| **Batch / contextos**   | `-x FILE`, `--directives FILE`                                | Ejecuta un archivo de directivas con bloques `[context]`. Cada `-x` inicia un entorno aislado. Repetible.                                                                                                                                                                                          |
| **Miscelánea**          | `--upgrade`                                                   | Auto‑actualiza *ghconcat* desde el repo oficial en `~/.bin`.                                                                                                                                                                                                                                       |
|                         | `--help`                                                      | Muestra ayuda integrada y sale.                                                                                                                                                                                                                                                                    |

**Pistas**

* Un `·` al final de la lista original indica opción **repetible** (todas las repetibles están anotadas arriba).
* Cualquier token posicional que **no** empiece con `-` se expande automáticamente a `-a <token>`.
* Cualquier flag que tome valor puede neutralizarse en un hijo pasando `none` (ej. `-t none`).
* Todos los mensajes de log (INFO / ERROR) se emiten a **stderr**; redirige con `2>/dev/null` si necesitas un dump
  limpio.
* Cuando `-y` y `-Y` aplican al mismo texto, **las reglas preserve ganan**: el segmento se restaura tras todos los
  reemplazos.

---

## 6 · Modelo Conceptual

```
[a/include] → [A/exclude] → [s/S suffix] → clean‑up → substitution (-y/-Y) → slicing
                                          ↓
                       +──────── template (‑t) ──────+
                       |                             |
                       |        IA (--ai)            |
                       +───────────┬─────────────────+
                                   ↓
                               salida (‑o)
```

Las variables `‑e/-E` y alias de contexto pueden interpolarse **en cualquier etapa posterior**.

---

## 7 · Archivos de Directivas & Contextos

### 7.1 Sintaxis

```gctx
# Valores por defecto globales
-w .
-s .py -s .yml
-b

[backend]
-a src/backend
-C -i

[frontend]
-a src/frontend
-u javascript
```

* Cada `[nombre]` inicia un **contexto hijo** que hereda flags.
* Flags escalares sobrescriben; flags lista anexan; booleanos se “pegan” una vez habilitados.
* No heredables: `-o`, `-U`, `-L`, `--ai`.

### 7.2 Expansión automática de `‑a`

Dentro del archivo y en CLI, cualquier token **que no empiece con `‑`** se convierte en `‑a TOKEN`.
Esto permite mezclar rutas y flags de forma natural.

---

## 8 · Plantillas & Variables

| Fuente del placeholder                | Disponibilidad                              |
|---------------------------------------|---------------------------------------------|
| `{ctx}`                               | Salida final del contexto `ctx`             |
| `{_r_ctx}` / `{_t_ctx}` / `{_ia_ctx}` | Crudo / templateado / respuesta IA de `ctx` |
| `{ghconcat_dump}`                     | Concatenación de todos los contextos (raíz) |
| `$VAR`                                | Sustitución de entorno dentro de flags      |
| `‑e foo=BAR`                          | Variable local                              |
| `‑E foo=BAR`                          | Variable global                             |

En plantillas, escapa llaves con `{{`/`}}` para imprimir `{}` literal.

---

## 9 · Pasarela IA

| Aspecto         | Detalle                                                                                        |
|-----------------|------------------------------------------------------------------------------------------------|
| Activación      | `--ai` y `OPENAI_API_KEY`                                                                      |
| Modelo por def. | `o3`                                                                                           |
| Fuente prompt   | Dump renderizado + prompt sistema opcional (`--ai-system-prompt`) + seeds JSONL (`--ai-seeds`) |
| Salida          | Escrita en `‑o` (o temp) y expuesta como `{_ia_ctx}`                                           |
| Stub disable    | `GHCONCAT_DISABLE_AI=1` produce `"AI‑DISABLED"`                                                |

---

## 10 · Workspaces & Salidas

* `‑w` – donde se descubren los archivos.
* `‑W` – donde viven plantillas, prompts y salidas (por defecto `‑w`).
* Rutas relativas se resuelven contra `‑w`/`‑W` del contexto actual.

---

## 11 · Análisis Avanzado (PDFs, URLs Remotas & Repos Git)

### 11.1 · Ingesta de Hojas de Cálculo (.xls / .xlsx)

`ghconcat` puede leer libros Excel y convertir cada sheet en un volcado **TSV**:

* Cada sheet inicia con cabecera
  `===== <nombre sheet> =====`
* Celdas vacías → cadenas vacías para alinear columnas.
* Característica **solo lectura**: tu workbook no se modifica.
* Dependencias: `pandas` **más** un engine Excel (`openpyxl`, `xlrd` o `pyxlsb`).
  Si faltan paquetes, el archivo se omite y se loguea advertencia.

#### Ejemplo

```bash
# Concatena todos .xlsx en reports/ y quita líneas en blanco
ghconcat -s .xlsx -a reports -b -o tsv_bundle.txt
```

| Flag     | Comportamiento                                                                           |
|----------|------------------------------------------------------------------------------------------|
| `-f URL` | Fetch individual. Archivo en `.ghconcat_urlcache`; nombre inferido si hace falta.        |
| `-F URL` | Crawler con profundidad; sigue links en HTML; respeta sufijos activos **en** el rastreo. |
| `-d N`   | Profundidad máxima (defecto 2, `0` = sin links).                                         |
| `-D`     | Sigue links entre dominios.                                                              |
| Logs     | Mensajes `✔ fetched …` / `✔ scraped … (d=N)` via **stderr**. Silencia con `2>/dev/null`. |

### 11.2 · Repos **Git** remotos (`-g` / `-G`)

| Flag      | Comportamiento                                                           |
|-----------|--------------------------------------------------------------------------|
| `-g SPEC` | Clonado shallow en `.ghconcat_gitcache/` (uno por SPEC) y añade archivos |
|           | que cumplan filtros de sufijo. Sintaxis SPEC:                            |
|           | `URL[^BRANCH][/SUBPATH]` (ejemplos abajo).                               |
| `-G SPEC` | Excluye archivo o directorio dentro de un repo añadido con `-g`.         |

**Ejemplos**

```bash
# Repo completo, rama por defecto:
ghconcat -g https://github.com/pallets/flask.git -s .py

# Solo docs/ de main:
ghconcat -g https://github.com/pallets/flask/docs -s .rst

# Archivo único en rama dev:
ghconcat -g git@github.com:GAHEOS/ghconcat^dev/src/ghconcat.py -s .py
```

### 11.3 · Ingesta PDF (`.pdf`)

`ghconcat` entiende **PDF** nativamente:

* Primero intenta extracción de texto embebido vía `pypdf`.
* Si el archivo no tiene texto *y* existen **pdf2image + pytesseract**, cae a OCR por página (300 dpi).
* Cada página se agrega en orden de lectura; cabeceras muestran el filename.
* Funciona con toda limpieza, slicing y templating.

> **Tip** Instala extras solo si necesitas OCR:
> `pip install pypdf pdf2image pytesseract`

```bash
# Concatena todos los PDFs en docs/, quita líneas en blanco y envuelve en markdown
ghconcat -s .pdf -a docs -b -u markdown -o manuals.md
```

---

## 12 · Recetas

<details>
<summary>12.1 Dump diff‑friendly para code‑review</summary>

```bash
# rama main
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# rama feature
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary>12.2 “Fuente‑de‑la‑verdad” Markdown</summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary>12.3 Pipeline de contextos con post‑proceso IA</summary>

```gctx
[concat]
-w .
-a src
-s .py -C -i
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
<summary>12.4 Bundle remoto + local</summary>

```bash
ghconcat -a src -s .py \
         -F https://gaheos.com/docs -d 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

<details>
<summary>12.5 Pipeline de síntesis académica a gran escala 📚🤖 (one‑shot `‑x`)</summary>

> Esta receta muestra cómo **un solo archivo de directivas** orquesta un flujo de trabajo académico end‑to‑end
> potenciado por múltiples “personas” LLM.
> Se realizará:
>
> 1. Recolección de fuentes primarias locales **y** URLs OA remotas.
> 2. Un *investigador junior* crea la primera síntesis.
> 3. Un *investigador senior* la refina.
> 4. Un *crítico académico* desafía las afirmaciones.
> 5. Un *editor de lenguaje* mejora claridad y estilo.
> 6. El crítico **otra vez** para peer‑review final.
> 7. Guarda el informe pulido para iteración humana.

El flujo completo está en **`academic_pipeline.gctx`** (ver abajo).
Todos los artefactos intermedios viven en el *workspace*; cada etapa puede reutilizar la anterior con
`-a workspace/<file>` **o** referenciando alias de contexto en plantillas (`{junior}`, `{senior}`, …).

#### Ejecución

```bash
ghconcat -x academic_pipeline.gctx -O
# El manuscrito final aparece en STDOUT y también en workspace/final_report.md
```

---

#### `academic_pipeline.gctx`

```text
// ======================================================================
//  ghconcat academic pipeline – Ejemplo Quantum Computing
// ======================================================================

# Valores globales -------------------------------------------------------
-w .                                    # raíz proyecto con notes/
-W workspace                            # prompts + outputs aparte
-E topic="Quantum Computing y Fotónica" # Visible en TODAS las plantillas

# -----------------------------------------------------------------------
# 0 · Recolectar corpus crudo  →  sources                                 //
# -----------------------------------------------------------------------
[sources]
// Dos papers OA (HTML render)
-F https://arxiv.org/abs/2303.11366     # Integrated Photonics for Quantum Computing
-F https://arxiv.org/abs/2210.10255     # Boson sampling in the noisy intermediate scale
-d 0

-K                                      # limpiar texto (quitar html, scripts, etc)
-s .html -C -i -u web-research -h       # clean & wrap
-o sources.md                           # expuesto como {sources}

[notes]
-a notes/
-s .md -u note -h                       # clean & wrap
-o notes.md                             # expuesto como {sources}

# -----------------------------------------------------------------------
# 1 · Borrador investigador junior  →  junior                             //
# -----------------------------------------------------------------------
[junior]
-a workspace/sources.md
-a workspace/notes.md
-t prompts/junior.md
--ai --ai-model o3
-o junior.out.md

# -----------------------------------------------------------------------
# 2 · Pasada investigador senior  →  senior                               //
# -----------------------------------------------------------------------
[senior]
-a workspace/junior.out.md
-t prompts/senior.md
--ai --ai-model gpt-4o
-o senior.out.md
-E to_critic=$senior

# -----------------------------------------------------------------------
# 3 · Primera crítica académica  →  critic1                               //
# -----------------------------------------------------------------------
[critic1]
-a workspace/senior.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic1.out.md

# -----------------------------------------------------------------------
# 4 · Pulido de lenguaje & estilo  →  redraft                             //
# -----------------------------------------------------------------------
[redraft]
-a workspace/critic1.out.md
-t prompts/editor.md
--ai --ai-model gpt-4o
-o redraft.out.md

# -----------------------------------------------------------------------
# 5 · Crítica final tras pulido  →  critic2                               //
# -----------------------------------------------------------------------
[critic2]
-a workspace/redraft.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic2.out.md
-E to_critic=$redraft

# -----------------------------------------------------------------------
# 6 · Bundle para humanos  →  final                                       //
# -----------------------------------------------------------------------
[final]
-a workspace/critic2.out.md
-h -R                                     # banner ruta absoluta
-o final_report.md
```

#### Archivos de prompt

> Guárdalos bajo `prompts/`.
> Cada plantilla puede acceder a:
>
> * `{topic}` – variable global `‑E`.
> * `{sources}`, `{junior}`, `{senior}`, … – alias de contexto.

##### prompts/junior.md

````markdown
### Rol

Eres un **investigador junior** preparando una revisión inicial sobre **{topic}**.

### Tarea

1. Lee el corpus en bloques ```note``` y ```web-research```.
2. Extrae **preguntas clave**, **metodologías** y **principales hallazgos**.
3. Devuelve un *esquema numerado* (máx 1 000 palabras).

{notes}
{sources}
````

##### prompts/senior.md

```markdown
### Rol

Eres un **investigador senior** mentorizando a un colega junior.

### Tarea

Mejora el borrador:

* Fusiona puntos redundantes.
* Añade trabajos seminales faltantes.
* Señala debilidades metodológicas.

Devuelve esquema revisado con comentarios inline.

### Contexto web‑research

{source}

### Notas junior

{notes}

### Borrador

{junior}
```

##### prompts/critic.md

```markdown
### Rol

Formas parte de un *comité de peer‑review*.

### Tarea

1. Evalúa coherencia lógica, soporte evidencial y novedad.
2. Destaca **inexactitudes** o citas faltantes.
3. Califica cada sección (A–D) y justifica en 30 palabras.

Documento bajo revisión:

{to_critic}
```

##### prompts/editor.md

```markdown
### Rol

**Editor científico** profesional.

### Tarea

Reescribe para claridad, concisión y tono académico formal.  
Corrige voz pasiva, ajusta oraciones y asegura estilo IEEE.

## Resumen de la crítica

{critic1}

## Documento revisado

Fuente (revisado críticamente):
{senior}
```

##### notes/note\_lab\_log\_2025-06-03.md

```markdown
# Bitácora de laboratorio – 3 Jun 2025

*Guías de onda de nitruro de silicio integradas para entrelazamiento on‑chip*

## Objetivo

Probar el lote Si₃N₄ (run #Q-0601) para pérdida, birrefringencia y visibilidad de interferencia de dos fotones.

## Configuración

| Ítem         | Modelo                      | Notas         |
|--------------|-----------------------------|---------------|
| Láser bomba  | TOPTICA iBeam-Smart 775 nm  | 10 mW CW      |
| Cristal PPLN | Periodo = 7.5µm             | SPDC Type‑0   |
| Montaje chip | Control temp. (25 ± 0.01°C) | –             |
| Detectores   | Par SNSPD, η≈80%            | Jitter ≈ 35ps |

## Resultados clave

* Pérdida de propagación **1.3 dB ± 0.1 dB cm⁻¹** @ 1550 nm.
* Visibilidad HOM **91 %** sin filtrado espectral.
* Sin birrefringencia apreciable dentro ±0.05 nm.

> **TODO**: simular dispersión para espirales 3 cm; programar ajustes e‑beam.
```



##### notes/note\_conference\_summary\_QIP2025.md

```markdown
# QIP 2025 – Resumen sesión Hot‑topic

*Tokio, 27 Ene 2025*

## 1. Boson Sampling >100 Fotones

**Ponente:** Jian‑Wei Pan

* 1 × 10⁻²₃ bound con interferómetro 144‑modo.
* Multiplexación temporal; reduce huella 40 ×.

## 2. Qubits fotónicos con corrección de error

**Ponente:** Stefanie Barz

* Código **[[4,2,2]]** dual‑rail con 97 % fidelidad.
* Crecimiento cluster‑state 10⁶ time‑bins.

## 3. Transducción NV‑Photon

**Ponente:** M. Atatüre

* Acoplamiento evanescente diamante‑SiN, g≈30 MHz.
* Perspectiva: entrega Bell determinista a >10 km.

### Tendencias

* PPLN integrados y LiNbO₃ delgado dominan.
* Migración de óptica bulk a plataformas heterogéneas III‑V + SiN.
* Mantra: **“mitigación antes de corrección de error”**.
```

##### notes/note\_review\_article\_highlights.md

```markdown
# Destacados – Review: *“Photonic Quantum Processors”* (Rev. Mod. Phys. 97, 015005 (2025))

| Sección            | Conclusión                                                              | Preguntas abiertas                                        |
|--------------------|-------------------------------------------------------------------------|-----------------------------------------------------------|
| Puertas lineales   | CNOT determinista >90dB aún un sueño; aproximaciones híbridas prometen. | ¿Pueden SNSPD η_det ≥95% + multiplexado cerrar la brecha? |
| Fuentes integradas | Micro‑anillos χ² on‑chip 300MHz @ 40mW.                                 | ¿Cross‑talk térmico >100 fuentes?                         |
| Modelos de error   | Desfase domina sobre pérdida en guías confinadas.                       | Benchmark unificado entre fundiciones.                    |
| Aplicaciones       | Ventaja near‑term en inference ML fotónica.                             | Trade‑off energía/latencia vs aceleradores silicio AI.    |

### Crítica del autor

El review omite desafíos de criopackaging y el *costo* real de SiN ultra‑low‑loss (≤0.5 dB m⁻¹). Incluir LCA
comparativo.
```

##### ¿Qué ocurrió?

| Etapa     | Input                 | Plantilla         | IA? | Output (alias)    |
|-----------|-----------------------|-------------------|-----|-------------------|
| `sources` | Notas + 2 ArXiv       | — (concat crudo)  | ✗   | `{sources}`       |
| `junior`  | `sources.md`          | `junior.md`       | ✔   | `{junior}`        |
| `senior`  | `junior.md`           | `senior.md`       | ✔   | `{senior}`        |
| `critic1` | `senior.md`           | `critic.md`       | ✔   | `{critic1}`       |
| `redraft` | `critic1.md`          | `editor.md`       | ✔   | `{redraft}`       |
| `critic2` | `redraft.md`          | `critic.md`       | ✔   | `{critic2}`       |
| `final`   | `critic2.md` (sin IA) | — (banner+concat) | ✗   | `final_report.md` |

El manuscrito es **totalmente trazable**: cada archivo intermedio se preserva, cabeceras con rutas absolutas y puedes
repetir cualquier etapa cambiando flags o modelo.

¡Feliz investigación!

</details>

---

## 13 · Resolución de Problemas

| Síntoma               | Pista                                                                |
|-----------------------|----------------------------------------------------------------------|
| Dump vacío            | Verifica rutas `‑a` y filtros de sufijo.                             |
| Timeout ChatGPT       | Chequea red, cuota o tamaño de prompt (>128k tokens).                |
| `{var}` sin resolver  | Define con `‑e`/`‑E` o asegura que alias exista.                     |
| Cabeceras duplicadas  | No mezcles `‑h` y líneas header dentro de plantillas personalizadas. |
| Imports persisten     | Usa `‑i` y/o `‑I` para el lenguaje adecuado.                         |
| Demasiados fetch      | Ajusta filtros `-s`/`-S` o reduce `-d`.                              |
| Git clone obsoleto    | Borra `.ghconcat_gitcache` o ejecuta sin `--preserve-cache`.         |
| Replace no ejecuta    | Asegura SPEC con **slashes** (`/…/`) y sin bloqueo `-Y`.             |
| Texto preservado mutó | Verifica flags iguales (`i`, `m`, …) en `-y` y `-Y`.                 |

---

## 14 · Entorno & Códigos de Salida

| Variable              | Propósito                                |
|-----------------------|------------------------------------------|
| `OPENAI_API_KEY`      | Habilita `--ai`.                         |
| `GHCONCAT_DISABLE_AI` | `1` fuerza stub (sin red).               |
| `DEBUG`               | `1` imprime traceback Python en errores. |

| Código | Significado           |
|--------|-----------------------|
| 0      | Éxito                 |
| 1      | Error fatal           |
| 130    | Interrumpido (Ctrl‑C) |

---

## 15 · Guía de Contribución

* Estilo: `ruff` + `mypy --strict` + *black* default.
* Tests: `python -m unittest -v` (o `pytest -q`).
* Formato commit: `feat: add wrap‑U flag` (imperativo, sin punto final).
* Para refactors grandes abre un issue primero – ¡contribuciones bienvenidas!

---

## 16 · Licencia

Distribuido bajo la **GNU Affero General Public License v3.0 o posterior (AGPL‑3.0‑or‑later)**.

Copyright © 2025 GAHEOS S.A.
Copyright © 2025 Leonardo Gavidia Guerra

Consulta el archivo [`LICENSE`](./LICENSE) para el texto completo.
