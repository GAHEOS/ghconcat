# ghconcat

> **Concatenador jerárquico, agnóstico al lenguaje · ultra‑determinista · sin dependencias externas**

`ghconcat` recorre tu árbol de proyecto, selecciona únicamente los archivos que te interesan, **elimina el ruido** (
comentarios, imports, líneas en blanco, etc.), aplica un recorte opcional por rangos de líneas y concatena el resultado
en un único volcado reproducible.
Casos de uso típicos:

* Prompts enormes pero limpios para LLMs.
* Artefactos trazables en CI/CD.
* Paquetes de revisión de código que mantienen los números de línea estables.
* Una *fuente de la verdad* que puedes incrustar en documentación o bases de conocimiento.

---

## 0 · TL;DR – Chuleta rápida

```bash
# 1 ─ Local + remoto: volcar .py + .xml bajo addons/ y web/, TAMBIÉN rastrear
#     https://gaheos.com hasta dos niveles de profundidad, envolver en Markdown, enviar a OpenAI:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -F https://gaheos.com -d 2 \
         -u markdown \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Dry‑run: listar cada HTML descubierto accesible desde la página principal
ghconcat -F https://gaheos.com -s .html -l

# 3 ─ Pipeline declarativo de varios pasos con contextos
ghconcat -x conf/pipeline.gctx -o build/artifact.txt
```

---

## Tabla de Contenidos

1. [Filosofía](#1--filosofía)
2. [Soporte ampliado de lenguajes y formatos](#2--soporte-ampliado-de-lenguajes-y-formatos-de-datos)
3. [Instalación](#3--instalación)
4. [Inicio rápido](#4--inicio-rápido)
5. [Referencia CLI](#5--referencia-cli)
6. [Modelo conceptual](#6--modelo-conceptual)
7. [Archivos de directivas y contextos](#7--archivos-de-directivas-y-contextos)
8. [Plantillas y variables](#8--plantillas-y-variables)
9. [Pasarela de IA](#9--pasarela-de-ia)
10. [Workspaces y salidas](#10--workspaces-y-salidas)
11. [Ingesta remota de URL y scraping](#11--ingesta-remota-de-url-y-scraping)
12. [Recetas](#12--recetas)
13. [Solución de problemas](#13--solución-de-problemas)
14. [Entorno y códigos de salida](#14--entorno-y-códigos-de-salida)
15. [Guía de contribución](#15--guía-de-contribución)
16. [Licencia](#16--licencia)

---

## 1 · Filosofía

| Principio                  | Razonamiento                                                                                 |
|----------------------------|----------------------------------------------------------------------------------------------|
| **Determinismo primero**   | Mismo input ⇒ volcado idéntico – perfecto para detección de desviaciones en CI.              |
| **Componible por diseño**  | Combina one‑liners, archivos de directivas (`‑x`) y contextos jerárquicos en un solo script. |
| **Solo lectura & atómico** | Tus fuentes nunca se tocan; la salida se escribe solo donde tú indiques (`‑o`).              |
| **Listo para LLM**         | Un único flag (`--ai`) enlaza el volcado a OpenAI.                                           |
| **Cero dependencias**      | Python puro ≥ 3.8. El puente a OpenAI es opcional (`pip install openai`).                    |

---

## 2 · Soporte ampliado de lenguajes y formatos de datos

El mapa de reglas de comentarios cubre **más de 30 lenguajes y formatos de datos** populares, permitiendo eliminar
comentarios e imports/exports con precisión en un código full‑stack moderno.

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

| Funcionalidad         | Paquete extra        |
|-----------------------|----------------------|
| Puente a OpenAI       | `pip install openai` |
| Fetch/scrape de URL\* | `urllib` (stdlib)    |

\* Todo el networking se basa en la librería estándar de Python.

---

## 4 · Inicio rápido

| Objetivo                                      | Comando                                                                                  |
|-----------------------------------------------|------------------------------------------------------------------------------------------|
| Concatenar todos los **.py** bajo `src/`      | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Auditar un volcado limpio de un *add‑on* Odoo | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Ejecución en modo listado                     | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Envolver & chatear con GPT                    | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Pipeline de contexto                          | `ghconcat -x ci_pipeline.gctx -o build/ci_bundle.txt`                                    |

---

## 5 · Referencia CLI

| Categoría               | Flag(s) (corta / larga)              | Propósito detallado                                                                                                                                   |
|-------------------------|--------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Localización**        | `-w DIR`, `--workdir DIR`            | Directorio raíz donde se descubren los archivos de contenido. Todas las rutas relativas del contexto actual se resuelven desde aquí.                  |
|                         | `-W DIR`, `--workspace DIR`          | Carpeta que almacena plantillas, prompts y salidas; por defecto es *workdir* si se omite.                                                             |
| **Descubrimiento**      | `-a PATH`, `--add-path PATH`         | Añade un archivo **o** directorio (recursivo) al set de inclusión. Repetible.                                                                         |
|                         | `-A PATH`, `--exclude-path PATH`     | Excluye un árbol de directorio completo aunque haya sido incluido por un `-a` más amplio. Repetible.                                                  |
|                         | `-s SUF`, `--suffix SUF`             | Lista blanca de extensiones (ej. `.py`). Al menos un `-s` convierte el filtro de sufijos en “solo permitir”. Repetible.                               |
|                         | `-S SUF`, `--exclude-suffix SUF`     | Lista negra de extensiones sin importar su origen. Repetible.                                                                                         |
|                         | `-f URL`, `--url URL`                | *Fetch* de un único recurso remoto y caché como archivo local (nombre preservado o inferido por *Content-Type*). Repetible.                           |
|                         | `-F URL`, `--url-scrape URL`         | Crawler con profundidad limitada; descarga cada recurso enlazado que pase los filtros de sufijo/exclusión activos. Repetible.                         |
|                         | `-d N`, `--url-scrape-depth N`       | Profundidad máxima para `-F` (por defecto **2**; `0` = solo la página semilla).                                                                       |
|                         | `-D`, `--disable-same-domain`        | Levanta la restricción de mismo host al hacer scraping; se siguen dominios externos.                                                                  |
| **Recorte de líneas**   | `-n NUM`, `--total-lines NUM`        | Mantiene como máximo `NUM` líneas por archivo *después* del ajuste de cabecera.                                                                       |
|                         | `-N LINE`, `--start-line LINE`       | Comienza la concatenación en la línea `LINE` (base 1; combinable con `-n`).                                                                           |
|                         | `-m`, `--keep-first-line`            | Conserva siempre la primera línea original aunque el recorte empiece después.                                                                         |
|                         | `-M`, `--no-first-line`              | Elimina forzosamente la primera línea original, sobreescribiendo un `-m` heredado.                                                                    |
| **Limpieza**            | `-c`, `--remove-comments`            | Elimina **solo** comentarios inline (sensibles al lenguaje).                                                                                          |
|                         | `-C`, `--remove-all-comments`        | Elimina comentarios inline **y** de línea completa.                                                                                                   |
|                         | `-i`, `--remove-import`              | Elimina sentencias `import` / `require` / `use` (Python, JS, Dart, …).                                                                                |
|                         | `-I`, `--remove-export`              | Elimina declaraciones `export` / `module.exports` (JS, TS, …).                                                                                        |
|                         | `-b`, `--strip-blank`                | Borra líneas en blanco dejadas tras la limpieza.                                                                                                      |
|                         | `-B`, `--keep-blank`                 | Preserva líneas en blanco (anula un `-b` heredado).                                                                                                   |
| **Plantillas & salida** | `-t FILE`, `--template FILE`         | Renderiza el volcado crudo a través de una plantilla tipo Jinja‑lite. Los placeholders se expanden después.                                           |
|                         | `-o FILE`, `--output FILE`           | Escribe el resultado final en disco; la ruta se resuelve respecto al *workspace*.                                                                     |
|                         | `-u LANG`, `--wrap LANG`             | Envuelve cada cuerpo de archivo en un bloque de código con `LANG` como info‑string.                                                                   |
|                         | `-U`, `--no-wrap`                    | Cancela un wrap heredado en un contexto hijo.                                                                                                         |
|                         | `-h`, `--header`                     | Emite cabeceras gruesas (`===== path =====`) la primera vez que aparece cada archivo.                                                                 |
|                         | `-H`, `--no-headers`                 | Suprime cabeceras en el contexto actual.                                                                                                              |
|                         | `-r`, `--relative-path`              | Muestra las rutas de cabecera relativas al *workdir* (por defecto).                                                                                   |
|                         | `-R`, `--absolute-path`              | Muestra las rutas de cabecera como rutas absolutas del sistema de archivos.                                                                           |
|                         | `-l`, `--list`                       | *Modo listado*: imprime solo las rutas de los archivos descubiertos, una por línea.                                                                   |
|                         | `-L`, `--no-list`                    | Deshabilita un modo listado heredado.                                                                                                                 |
|                         | `-e VAR=VAL`, `--env VAR=VAL`        | Define una variable **local** visible solo en el contexto actual. Repetible.                                                                          |
|                         | `-E VAR=VAL`, `--global-env VAR=VAL` | Define una variable **global** heredada por contextos descendientes. Repetible.                                                                       |
| **Control STDOUT**      | `-O`, `--stdout`                     | Duplica siempre la salida final en STDOUT, incluso cuando `-o` está presente. Si `-o` falta en la raíz, el streaming a STDOUT ocurre automáticamente. |
| **Puente IA**           | `--ai`                               | Envía el texto renderizado a OpenAI Chat; la respuesta se escribe a `-o` (o archivo temporal) y se expone como `{_ia_ctx}` para plantillas.           |
|                         | `--ai-model NAME`                    | Selecciona el modelo de chat (por defecto **o3**).                                                                                                    |
|                         | `--ai-temperature F`                 | Temperatura de muestreo (ignorada para *o3*).                                                                                                         |
|                         | `--ai-top-p F`                       | Valor top‑p de muestreo nuclear.                                                                                                                      |
|                         | `--ai-presence-penalty F`            | Parámetro *presence‑penalty*.                                                                                                                         |
|                         | `--ai-frequency-penalty F`           | Parámetro *frequency‑penalty*.                                                                                                                        |
|                         | `--ai-system-prompt FILE`            | Archivo de prompt de sistema (con placeholders).                                                                                                      |
|                         | `--ai-seeds FILE`                    | Mensajes JSONL semilla para cebar el chat.                                                                                                            |
| **Batch / contextos**   | `-x FILE`, `--directives FILE`       | Ejecuta un archivo de directivas que contiene bloques `[context]`. Cada `-x` inicia un entorno aislado. Repetible.                                    |
| **Miscelánea**          | `--upgrade`                          | Auto‑actualiza *ghconcat* desde el repo oficial a `~/.bin`.                                                                                           |
|                         | `--help`                             | Muestra la ayuda integrada y sale.                                                                                                                    |

**Pistas**

* Un `·` en la lista original de flags significa que la opción **puede repetirse** (todas las flags repetibles se
  señalan).
* Cualquier token posicional que **no** empiece por `-` se expande automáticamente a `-a <token>`.
* Cualquier flag que reciba valor puede neutralizarse en un contexto hijo pasando el literal `none` (ej. `-t none`).
* Todos los mensajes de log (INFO / ERROR) se emiten a **stderr**; redirígelos con `2>/dev/null` si necesitas un volcado
  limpio en STDOUT.

---

## 6 · Modelo conceptual

```
[a/include] → [A/exclude] → [s/S suffix] → clean‑up → slicing
                                          ↓
                       +──────── plantilla (‑t) ──────+
                       |                              |
                       |           IA (--ai)          |
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
-C -i

[frontend]
-a src/frontend
-u javascript
```

* Cada `[name]` inicia un **contexto hijo** que hereda flags.
* Flags escalares sobrescriben; flags de lista se añaden; booleanos se mantienen una vez habilitados.
* No heredados: `-o`, `-U`, `-L`, `--ai`.

### 7.2 Expansión automática de `‑a`

Dentro del archivo y en la CLI, cualquier token **que no empiece con `‑`** se convierte en `‑a TOKEN`.
Esto permite mezclar rutas y flags con naturalidad.

---

## 8 · Plantillas y variables

| Fuente del placeholder                | Disponibilidad                                    |
|---------------------------------------|---------------------------------------------------|
| `{ctx}`                               | Salida final del contexto `ctx`                   |
| `{_r_ctx}` / `{_t_ctx}` / `{_ia_ctx}` | Crudo / con plantilla / respuesta de IA           |
| `{ghconcat_dump}`                     | Concatenación de todos los contextos (solo root)  |
| `$VAR`                                | Sustitución de entorno dentro de valores de flags |
| `‑e foo=BAR`                          | Variable local                                    |
| `‑E foo=BAR`                          | Variable global                                   |

En plantillas, escapa llaves con `{{`/`}}` para imprimir un `{}` literal.

---

## 9 · Pasarela de IA

| Aspecto         | Detalle                                                                                  |
|-----------------|------------------------------------------------------------------------------------------|
| Activación      | `--ai` y `OPENAI_API_KEY`                                                                |
| Modelo por def. | `o3`                                                                                     |
| Origen prompt   | Volcado renderizado + prompt de sistema opcional (`--ai-system-prompt`) + semillas JSONL |
| Salida          | Escrito a `‑o` (o temporal) y expuesto como `{_ia_ctx}`                                  |
| Stub desactivar | `GHCONCAT_DISABLE_AI=1` produce `"AI‑DISABLED"`                                          |

---

## 10 · Workspaces y salidas

* `‑w` – dónde se descubren los archivos.
* `‑W` – dónde viven plantillas, prompts y outputs (por defecto `‑w`).
* Las rutas relativas se resuelven contra el `‑w/‑W` del contexto actual.

---

## 11 · Ingesta remota de URL y scraping

| Flag     | Comportamiento                                                                                  |
|----------|-------------------------------------------------------------------------------------------------|
| `-f URL` | Fetch único. Archivo guardado en `.ghconcat_urlcache`; nombre inferido si es necesario.         |
| `-F URL` | Crawler con profundidad; sigue enlaces en HTML; respeta filtros de sufijo **durante** el crawl. |
| `-d N`   | Profundidad máxima (por defecto 2, `0` = solo semilla).                                         |
| `-D`     | Sigue enlaces entre dominios.                                                                   |
| Logs     | Mensajes `✔ fetched …` / `✔ scraped … (d=N)` en **stderr**. Silencia con `2>/dev/null`.         |

## 12 · Recetas

<details>
<summary>11.1 Volcado diff‑friendly para revisión de código</summary>

```bash
# rama main
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# rama feature
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary>11.2 Markdown “fuente‑de‑la‑verdad”</summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary>11.3 Pipeline de contexto con post‑procesamiento IA</summary>

```gctx
[concat]
-w .
-a src
-s .py -C -i
-o concat.out.md

[humanize]
-a workspace/concat.out.md
-t tpl/humanize.md
--ai --ai-model o3
-o human.out.md

[qa]
-W qa_workspace
-a workspace/human.out.md
-t tpl/qa_check.md
--ai --ai-model o3
-o report.md
```

```bash
ghconcat -x pipeline.gctx
```

</details>

<details>
<summary>11.4 Bundle remoto + local</summary>

```bash
ghconcat -a src -s .py \
         -F https://gaheos.com/docs -d 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

<details>
<summary>11.5 Pipeline de síntesis de literatura académica a gran escala 📚🤖 (one‑shot `‑x`)</summary>

> Este ejemplo muestra cómo **un único archivo de directivas** orquesta un flujo académico de extremo a extremo
> impulsado por múltiples “personas” LLM.
> Haremos:
>
> 1. Recolectar fuentes primarias locales **y** URLs open‑access.
> 2. Dejar que un *investigador junior* cree la síntesis inicial.
> 3. Pedir a un *investigador senior* que la refine.
> 4. Invitar a un *crítico académico* a desafiar las afirmaciones.
> 5. Aplicar un *editor de lenguaje* para mejorar claridad y estilo.
> 6. Llamar al crítico **otra vez** para una revisión final.
> 7. Guardar el informe pulido para que el equipo humano itere.

El flujo completo está en **`academic_pipeline.gctx`** (ver abajo).
Todos los artefactos intermedios viven en el *workspace*; cada etapa puede reutilizar la anterior bien mediante
`-a workspace/<file>` **o** referenciando el alias de contexto en una plantilla (`{junior}`, `{senior}`, …).

#### Ejecútalo

```bash
ghconcat -x academic_pipeline.gctx -O
# El manuscrito final aparece en STDOUT y también en workspace/final_report.md
```

---

#### `academic_pipeline.gctx`

```text
// ======================================================================
//  ghconcat academic pipeline – Ejemplo de Computación Cuántica
//  Toda ruta que no comience con “-” se expande a “-a <ruta>”.
// ======================================================================

# Configuración global ---------------------------------------------------
-w .                                   # raíz del proyecto conteniendo notes/
-W workspace                           # prompts + outputs separados
-E topic="Quantum Computing and Photonics"  # Visible en *todas* las plantillas

# -----------------------------------------------------------------------
# 0 · Reunir corpus bruto  →  sources                                    //
# -----------------------------------------------------------------------
[sources]
// Dos papers open‑access (render HTML)
-F https://arxiv.org/abs/2303.11366     # Integrated Photonics for Quantum Computing
-F https://arxiv.org/abs/2210.10255     # Boson sampling in the noisy intermediate scale
-d 0

-K                                      # limpiar texto (quitar html, scripts, etc)
-s .html -C -i -u web-research -h       # limpiar & envolver
-o sources.md                           # expuesto como {sources}

[notes]
-a notes/
-s .md -u note -h                       # limpiar & envolver
-o notes.md                             # expuesto como {sources}

# -----------------------------------------------------------------------
# 1 · Borrador investigador junior  →  junior                            //
# -----------------------------------------------------------------------
[junior]
-a workspace/sources.md
-a workspace/notes.md
-t prompts/junior.md
--ai --ai-model o3
-o junior.out.md

# -----------------------------------------------------------------------
# 2 · Paso investigador senior  →  senior                                //
# -----------------------------------------------------------------------
[senior]
-a workspace/junior.out.md
-t prompts/senior.md
--ai --ai-model gpt-4o
-o senior.out.md
-E to_critic=$senior

# -----------------------------------------------------------------------
# 3 · Primera crítica académica  →  critic1                              //
# -----------------------------------------------------------------------
[critic1]
-a workspace/senior.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic1.out.md

# -----------------------------------------------------------------------
# 4 · Pulido de lenguaje y estilo  →  redraft                            //
# -----------------------------------------------------------------------
[redraft]
-a workspace/critic1.out.md
-t prompts/editor.md
--ai --ai-model gpt-4o
-o redraft.out.md

# -----------------------------------------------------------------------
# 5 · Crítica final tras pulido  →  critic2                              //
# -----------------------------------------------------------------------
[critic2]
-a workspace/redraft.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic2.out.md
-E to_critic=$redraft

# -----------------------------------------------------------------------
# 6 · Bundle para humanos  →  final                                      //
# -----------------------------------------------------------------------
[final]
-a workspace/critic2.out.md
-h -R                                  # cabecera con ruta absoluta
-o final_report.md
```

#### Archivos de prompt

> Guárdalos bajo `prompts/` (relativo al workspace).
> Cada plantilla puede acceder a:
>
> * `{topic}` – variable global definida con `‑E`.
> * `{sources}`, `{junior}`, `{senior}`, … – alias de contexto.

##### prompts/junior.md

````markdown
### Rol

Eres un **asociado de investigación junior** preparando una revisión inicial de literatura sobre **{topic}**.

### Tarea

1. Lee el corpus bruto localizado en los bloques de código ```note``` y ```web-research```.
2. Extrae **preguntas de investigación clave**, **metodologías** y **hallazgos principales**.
3. Devuelve un *esquema numerado* (máx. 1 000 palabras).

{notes}
{sources}
````

##### prompts/senior.md

```markdown
### Rol

Eres un **investigador principal senior** mentor de un colega junior.

### Tarea

Mejora el borrador siguiente:

* Fusionando puntos redundantes.
* Añadiendo trabajos seminales faltantes.
* Marcando debilidades metodológicas.

Devuelve un esquema revisado con comentarios inline donde se hagan cambios.

### Antecedentes web‑research

{source}

### Notas del junior

{notes}

### Borrador

{junior}
```

##### prompts/critic.md

```markdown
### Rol

Formas parte de un *comité de revisión por pares a ciegas*.

### Tarea

1. Evalúa críticamente coherencia lógica, soporte evidencial y originalidad.
2. Destaca **inexactitudes** o citas faltantes.
3. Califica cada sección (A–D) y justifica la nota en 30 palabras máx.

Documento en revisión:

{to_critic}
```

##### prompts/editor.md

```markdown
### Rol

**Editor profesional de ciencia**.

### Tarea

Reescribe el documento para claridad, concisión y tono académico formal.  
Corrige voz pasiva excesiva, ajusta frases y asegura estilo de referencia IEEE.

## Resumen de la crítica

{critic1}

## Documento revisado

Fuente (revisado críticamente):
{senior}
```

##### notes/note\_lab\_log\_2025-06-03.md

```markdown
# Registro de laboratorio – 3 Jun 2025

*Guías de onda de nitruro de silicio integradas para entrelazamiento on‑chip*

## Objetivo

Probar el lote de guías de onda Si₃N₄ (run #Q-0601) para pérdida, birrefringencia y visibilidad de interferencia de dos
fotones.

## Configuración

| Ítem          | Modelo                                 | Notas             |
|---------------|----------------------------------------|-------------------|
| Láser bomba   | TOPTICA iBeam-Smart 775 nm             | 10 mW CW          |
| Cristal PPLN  | Período = 7.5 µm                       | SPDC Tipo‑0       |
| Montaje chip  | Control de temperatura (25 ± 0.01 °C)  | –                 |
| Detectores    | Par SNSPD, η≈80%                      | Jitter ≈ 35 ps    |

## Resultados clave

* Pérdida de propagación **1.3 dB ± 0.1 dB cm⁻¹** @ 1550 nm (cut‑back).
* Visibilidad HOM **91 %** sin filtrado espectral (mejor hasta ahora).
* Sin birrefringencia apreciable dentro de ±0.05 nm de ajuste.

> **TODO**: simular dispersión para espirales de 3 cm; programar ajustes de máscara e‑beam.
```

##### notes/note\_conference\_summary\_QIP2025.md

```markdown
# QIP 2025 – Resumen de sesión hot‑topic

*Tokio, 27 Ene 2025*

## 1. Boson Sampling más allá de 100 fotones

**Ponente:** Jian‑Wei Pan

* Limite de dureza de muestreo 1 × 10⁻²₃ usando interferómetro de 144 modos.
* Introdujo multiplexación en dominio temporal; reduce huella 40 ×.

## 2. Qubits fotónicos con corrección de errores

**Ponente:** Stefanie Barz

* Código **[[4,2,2]]** en qubits dual‑rail con 97 % de fidelidad heraldada.
* Crecimiento de cluster‑state mediante puertas fusion‑II alcanzó 10⁶ time‑bins físicos.

## 3. Transducción NV‑Center a fotón

**Ponente:** M. Atatüre

* Acoplamiento evanescente diamante‑SiN on‑chip, g≈30 MHz.
* Perspectiva: entrega determinista de estados Bell a >10 km.

### Tendencias transversales

* PPLN integrado y LiNbO₃ de capa fina están **en todas partes**.
* Paso de óptica bulky a plataformas heterogéneas III‑V + SiN.
* Mantra comunitario: **“mitigación de errores antes de corrección de errores”**.
```

##### notes/note\_review\_article\_highlights.md

```markdown
# Destacados – Reseña: *“Procesadores Cuánticos Fotónicos”* (Rev. Mod. Phys. 97, 015005 (2025))

| Sección               | Conclusión clave                                                                                          | Preguntas abiertas                                                     |
|-----------------------|-----------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| Puertas lineales      | CNOT determinista sigue siendo un sueño >90dB; enfoques híbridos basados en medición son más prometedores.| ¿Pueden SNSPD η_det ≥ 95% + multiplexación temporal cerrar la brecha?  |
| Fuentes integradas    | Micro‑anillos χ² on‑chip: 300MHz de pares con p‑pump = 40mW.                                              | ¿Escalado de cross‑talk térmico más allá de 100 fuentes?               |
| Modelos de error      | Desfase domina sobre pérdida en guías fuertemente confinadas.                                             | Necesario benchmarking unificado entre foundries.                      |
| Aplicaciones          | Ventaja cercana en inferencia ML fotónica.                                                                | Compromiso energía/latencia vs aceleradores AI de silicio.             |

### Crítica del autor

La reseña pasa por alto los desafíos de criopackaging y el *coste real* de SiN ultrabaja pérdida (≤0.5 dB m⁻¹).  
Incluir datos comparativos de LCA en trabajos futuros.
```

##### ¿Qué acaba de ocurrir?

| Etapa     | Input                        | Plantilla           | IA | Salida (alias)    |
|-----------|------------------------------|---------------------|----|-------------------|
| `sources` | Notas locales + 2 ArXiv HTML | — (concat crudo)    | ✗  | `{sources}`       |
| `junior`  | `sources.md`                 | `junior.md`         | ✔  | `{junior}`        |
| `senior`  | `junior.md`                  | `senior.md`         | ✔  | `{senior}`        |
| `critic1` | `senior.md`                  | `critic.md`         | ✔  | `{critic1}`       |
| `redraft` | `critic1.md`                 | `editor.md`         | ✔  | `{redraft}`       |
| `critic2` | `redraft.md`                 | `critic.md`         | ✔  | `{critic2}`       |
| `final`   | `critic2.md` (sin IA)        | — (banner + concat) | ✗  | `final_report.md` |

El manuscrito final es **totalmente trazable**: cada archivo intermedio se preserva, las cabeceras muestran rutas
absolutas y puedes reproducir cualquier etapa re‑ejecutando su contexto con flags o modelo distinto.

¡Feliz investigación!

</details>

---

## 13 · Solución de problemas

| Síntoma              | Pista                                                           |
|----------------------|-----------------------------------------------------------------|
| Volcado vacío        | Verifica rutas `‑a` y filtros de sufijo.                        |
| Timeout en ChatGPT   | Revisa red, cuota o tamaño de prompt (>128k tokens?).          |
| `{var}` sin resolver | Define con `‑e`/`‑E` o asegura que exista el alias de contexto. |
| Cabeceras duplicadas | No mezcles `‑h` y líneas de cabecera en plantillas custom.      |
| Imports persisten    | Usa `‑i` y/o `‑I` según lenguaje.                               |
| Demasiados archivos  | Ajusta filtros `-s`/`-S` o reduce `-d`.                         |

---

## 14 · Entorno y códigos de salida

| Variable              | Propósito                        |
|-----------------------|----------------------------------|
| `OPENAI_API_KEY`      | Habilita `--ai`.                 |
| `GHCONCAT_DISABLE_AI` | `1` fuerza stub (sin red).       |
| `DEBUG`               | `1` imprime traceback de Python. |

| Código | Significado           |
|--------|-----------------------|
| 0      | Éxito                 |
| 1      | Error fatal           |
| 130    | Interrumpido (Ctrl‑C) |

---

## 15 · Guía de contribución

* Estilo: `ruff` + `mypy --strict` + *black* por defecto.
* Tests: `python -m unittest -v` (o `pytest -q`).
* Formato de commit: `feat: add wrap‑U flag` (imperativo, sin punto final).
* Para refactors grandes abre una issue primero – ¡contribuciones bienvenidas!

---

## 16 · Licencia

Distribuido bajo la **GNU Affero General Public License v3.0 o posterior (AGPL‑3.0‑or‑later)**.

Copyright © 2025 GAHEOS S.A.
Copyright © 2025 Leonardo Gavidia Guerra

Consulta el archivo [`LICENSE`](./LICENSE) para el texto completo de la licencia.
