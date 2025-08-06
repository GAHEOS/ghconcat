# ghconcat

> **Hierarchical, language‑agnostic file concatenator · ultra‑deterministic · zero external deps**

`ghconcat` recorre tu proyecto, selecciona los archivos que te interesan, **elimina el ruido** (comentarios, imports,
líneas vacías, etc.), aplica slicing por rango de líneas y concatena el resultado en un único *dump* reproducible.  
Usa ese dump para:

* alimentar LLMs con prompts gigantes pero limpios,
* generar artefactos trazables en CI/CD,
* producir bundles de revisión de código,
* o como “fuente de verdad” en tu documentación técnica.

---

## 0 · TL;DR – Quick Cheat‑Sheet

```bash
# 1 ─ Crear un dump de 120 líneas por archivo, incluyendo sólo .py y .xml
#     bajo addons/ y web/, envolver cada chunk en Markdown, pasar por OpenAI
#     y guardar la respuesta en ai/reply.md:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -u markdown \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Mismo descubrimiento, pero "dry‑run": listar rutas absolutas nada más
ghconcat -s .py -s .xml -a addons -l -R

# 3 ─ Pipeline multi‑paso 100% declarativo con contexts
ghconcat -x conf/pipeline.gcx -o build/artifact.txt
````

---

## Table of Contents

1. [Philosophy](#1--philosophy)
2. [What’s New in v2](#2--whats-new-in-v2)
3. [Installation](#3--installation)
4. [Quick Start](#4--quick-start)
5. [CLI Reference](#5--cli-reference)
6. [Conceptual Model](#6--conceptual-model)
7. [Directive Files & Contexts](#7--directive-files--contexts)
8. [Templating & Variables](#8--templating--variables)
9. [AI Gateway](#9--ai-gateway)
10. [Workspaces & Outputs](#10--workspaces--outputs)
11. [Recipes](#11--recipes)
12. [Migrating from v1](#12--migrating-from-v1)
13. [Troubleshooting](#13--troubleshooting)
14. [Environment & Exit Codes](#14--environment--exit-codes)
15. [Contribution Guide](#15--contribution-guide)
16. [License](#16--license)

---

## 1 · Philosophy

| Principle                | Why it matters                                                                               |
|--------------------------|----------------------------------------------------------------------------------------------|
| **Determinism first**    | Mismo input ⇒ mismo dump → perfecto para detectar desviaciones en CI.                        |
| **Composable by design** | Combina one‑liners, archivos de directivas (`‑x`) y contexts jerárquicos en el mismo script. |
| **Read‑only & atomic**   | Nunca toca tus fuentes; sólo escribe al path indicado con `‑o`.                              |
| **LLM‑ready**            | Un *flag* (`--ai`) basta para enviar el prompt a OpenAI.                                     |
| **0 deps**               | Sólo Python ≥3.8. El bridge OpenAI es opcional (`pip install openai`).                       |

---

## 2 · What’s New in v2

| Área                 | v1                                       | **v2 (this doc)**                                                      |
|----------------------|------------------------------------------|------------------------------------------------------------------------|
| **Batching**         | `‑X` (heredaba) vs `‑x` (in‑line)        | **Sólo `‑x`**; cada archivo es *sandbox* aislado, contexts con `[ctx]` |
| **Discovery flags**  | `‑g` / `‑G` por lenguaje                 | **Eliminados** → usa `‑s` / `‑S` por sufijo                            |
| **Whitespace**       | `‑B` preserva `\n`; no inverso explícito | `‑b` **podar** y `‑B` **preservar** (tri‑state por contexto)           |
| **First‑line rules** | `‑M` (mantener cabecera si cortabas)     | `‑m` **keep**, `‑M` **drop**                                           |
| **Header banner**    | Siempre on, se anulaba con `‑P`          | Off por defecto. Actívalo con `‑h`; anúlalo con `‑H`                   |
| **Path style**       | `‑p` absolutas / `‑P` sin encabezados    | `‑R` absolutas / `‑r` relativas (default)                              |
| **Wrap fences**      | `‑u` activaba, sin forma de anular       | `‑u LANG` activa · `‑U` anula                                          |
| **List mode**        | `‑l` (list)                              | `‑l` lista · `‑L` cancela herencia de `‑l`                             |
| **Env vars**         | `‑e/-E` propagaban siempre               | Ahora **sólo `‑E`** se hereda; `‑e` es local al contexto               |
| **Self‑upgrade**     | No existía                               | `--upgrade` descarga última versión a `~/.bin/ghconcat`                |

---

## 3 · Installation

<details>
<summary><strong>Linux / macOS / WSL</strong></summary>

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 -m pip install .
mkdir -p ~/.bin && cp ghconcat.py ~/.bin/ghconcat && chmod +x ~/.bin/ghconcat
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat --help
```

</details>

<details>
<summary><strong>Optional – enable OpenAI bridge</strong></summary>

```bash
python3 -m pip install openai
export OPENAI_API_KEY=sk-********************************
```

</details>

---

## 4 · Quick Start

| Goal / Task                                           | Command                                                                                  |
|-------------------------------------------------------|------------------------------------------------------------------------------------------|
| Concatenar todos los **.py** bajo `src/` → `dump.txt` | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Auditar un **addon Odoo**, sin comentarios ni imports | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Dry‑run (lista relativa)                              | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Dump `.py + .dart`, envolver y enviar a ChatGPT       | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Generar un artefacto multi‑paso                       | `ghconcat -x ci_pipeline.gcx -o build/ci_bundle.txt`                                    |

---

## 5 · CLI Reference

*Flags repetibles marcadas con **·***

| Category                | Flag(s) & Arg(s)                             | Description                                             |
|-------------------------|----------------------------------------------|---------------------------------------------------------|
| **Discovery**           | `‑w DIR` / `‑W DIR`                          | Raíz de contenido / workspace de templates & outputs    |
|                         | `‑a PATH`· / `‑A PATH`·                      | Incluir / excluir archivo o directorio                  |
|                         | `‑s SUF`· / `‑S SUF`·                        | Incluir / excluir por sufijo (`.py`, `.yml`, etc.)      |
| **Line Slicing**        | `‑n NUM`, `‑N LINE`                          | Máx. líneas / línea inicial                             |
|                         | `‑m` / `‑M`                                  | Mantener / descartar primera línea si entra en el slice |
| **Clean‑up**            | `‑c` / `‑C`                                  | Quitar comentarios simples / todos los comentarios      |
|                         | `‑i` / `‑I`                                  | Quitar imports / exports                                |
|                         | `‑b` / `‑B`                                  | Podar / preservar líneas en blanco                      |
| **Templating & Output** | `‑t FILE` / `‑t none`                        | Template Jinja‑lite; `none` anula herencia              |
|                         | `‑o FILE`                                    | Escribir resultado                                      |
|                         | `‑u LANG` / `‑U`                             | Wrap fenced `LANG` / anular wrap heredado               |
|                         | `‑h` / `‑H`                                  | Mostrar / ocultar encabezados pesados                   |
|                         | `‑r` / `‑R`                                  | Rutas relativas / absolutas en header                   |
|                         | `‑l` / `‑L`                                  | Modo lista / cancelar lista heredada                    |
|                         | `‑e VAR=VAL`· / `‑E VAR=VAL`·                | Variable local / global                                 |
| **AI Bridge**           | `--ai`                                       | Activar envio a OpenAI                                  |
|                         | `--ai-model`, `--ai-temperature`, ...        | Parámetros del modelo                                   |
|                         | `--ai-system-prompt FILE`, `--ai-seeds FILE` | Prompt del sistema & seeds JSONL                        |
| **Batching**            | `‑x FILE`·                                   | Ejecutar archivo de directivas (contextos incluidos)    |
| **Misc**                | `--upgrade`                                  | Auto‑actualizar ghconcat                                |

*Any value‑flag accepts `none` to cancel an inherited value.*

---

## 6 · Conceptual Model

```
[a/include] → [A/exclude] → [s/S suffix] → clean‑up → slicing
                                          ↓
                       +──────── template (‑t) ──────+
                       |                             |
                       |        AI (--ai)            |
                       +───────────┬─────────────────+
                                   ↓
                               output (‑o)
```

`‑e/-E` variables y aliases de contexto pueden interpolarse *en cualquier etapa* posterior.

---

## 7 · Directive Files & Contexts

### 7.1 The `‑x` file

* Un `‑x` abre un **entorno aislado**; sus flags no se filtran al siguiente `‑x`.
* Dentro del archivo, cada línea es parseada como CLI; los contexts se definen con `[name]`.

```gcx
# global defaults
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

**Reglas de herencia**

| Tipo         | Combinación hijo ⊕ padre         |
|--------------|----------------------------------|
| Listas       | concatena (`suffix`, `add_path`) |
| Booleanos    | OR (una vez activo, no se apaga) |
| Escalares    | hijo sobreescribe (`‑w`, `‑t`)   |
| No‑heredados | `‑o`, `--ai`, `‑U`, `‑L`         |

Las variables locales (`‑e`) **no** se propagan; las globales (`‑E`) sí.

---

## 8 · Templating & Variables

* Cualquier placeholder `{var}` se reemplaza usando:

    * Aliases de contexto (`[ctx]` crea `{ctx}`, `{_r_ctx}`, `{_t_ctx}`, `{_ia_ctx}`)
    * `ghconcat_dump` (concat global de todos los contexts)
    * Variables de `‑e` (local) y `‑E` (global)
* Expansión de `$VAR` aplica a los propios flags antes de parsear.

---

## 9 · AI Gateway

| Aspect        | Detail                                              |
|---------------|-----------------------------------------------------|
| Activación    | `--ai` + `OPENAI_API_KEY` en entorno                |
| Modelos       | Cualquiera soportado (def. **o3**)                  |
| Seeds JSONL   | Heredan salvo `--ai-seeds none`                     |
| System prompt | Template‑aware (`--ai-system-prompt`)               |
| Timeout       | 1800s (config en código)                           |
| Salida        | Se escribe a `‑o` (o tmpfile) y se asigna `_ia_ctx` |

> ⚠️ Toda la cadena de prompt se envía tal cual al proveedor LLM.

---

## 10 · Workspaces & Outputs

* `‑w` define la raíz de búsqueda de contenido.
* `‑W` es el *workspace* relativo a `‑w` (templates, prompts, outputs).
* Paths relativos dentro de un context se resuelven respecto a los valores vigentes de `‑w` / `‑W` en ese nivel.

---

## 11 · Recipes

<details>
<summary><strong>11.1 Diff‑friendly dump for code‑review</strong></summary>

```bash
# main branch
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# feature branch
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>11.2 Generate “source‑of‑truth” markdown</strong></summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary><strong>11.3 Context pipeline with AI post‑processing</strong></summary>

```gcx
[concat]
-w .
-a src
-s .py -C -i
-o concat.out.md

[humanize]
-a workspace/concat.out.md
-t tpl/humanize.md
--ia
-o human.out.md

[qa]
-W qa_workspace
-a workspace/human.out.md
-t tpl/qa_check.md
--ia
-o report.md
```

```bash
ghconcat -x pipeline.gcx
```

</details>

---

## 12 · Migrating from v1

| v1 Flag / Concept | Replacement in v2         |
|-------------------|---------------------------|
| `‑g / ‑G`         | `‑s / ‑S` + sufijo puro   |
| `‑X`              | `‑x` + contexts `[ctx]`   |
| `‑M` (first line) | `‑m` (keep) / `‑M` (drop) |
| `‑P`              | `‑H` (ocultar header)     |
| `‑p`              | `‑R` (absoluto) / `‑r`    |
| `‑u none`         | `‑U`                      |

Ejemplo rápido:

```bash
# v1
ghconcat -g py -C -i -n 80 -a src -X bundle.gcx

# v2
ghconcat -s .py -C -i -n 80 -a src -x bundle.gcx
```

---

## 13 · Troubleshooting

| Symptom                                  | Hint                                                             |
|------------------------------------------|------------------------------------------------------------------|
| Dump vacío                               | ¿`‑a` / `‑s` correctos? Revisa exclusiones `‑A/‑S`.              |
| ChatGPT timeout                          | Net, cuota o prompt >128k tokens.                                |
| Variable no resuelta en template `{foo}` | Usa `‑e foo=bar` o alias de contexto.                            |
| Headers duplicados                       | No combines `‑h` en contexts con template root que duplique enc. |
| `flag expects VAR=VAL`                   | Revisa sintaxis en `‑e/-E`.                                      |
| Import / export aún presente             | Usa `‑i` y/o `‑I` según lenguaje.                                |

---

## 14 · Environment & Exit Codes

| Var                     | Purpose                             |
|-------------------------|-------------------------------------|
| `OPENAI_API_KEY`        | Habilita `--ai`.                    |
| `GHCONCAT_DISABLE_AI=1` | Fuerza stub local de IA (tests).    |
| `DEBUG=1`               | Stack‑trace en errores inesperados. |

| Code | Meaning                  |
|------|--------------------------|
| 0    | OK                       |
| 1    | Error fatal / validación |
| 130  | Cancelado vía Ctrl‑C     |

---

## 15 · Contribution Guide

* **Style**: `ruff` + `mypy --strict` + `black`.
* **Tests**: `python -m unittest -v`.
* Commits: `feat: add wrap‑U flag`.
* PRs welcome — abre issue antes de refactors grandes.

---

## 16 · License

MIT © GAHEOS S.A.
