# ghconcat

> **Concatenador jerárquico, multilenguaje y determinista · cero dependencias externas**

`ghconcat` recorre tu árbol de proyecto, selecciona sólo los archivos que te importan, **elimina el ruido**
(comentarios, imports, líneas en blanco, etc.), aplica un recorte opcional por rango de líneas y concatena el
resultado en un *dump* único y reproducible.
Casos de uso típicos:

* Prompts enormes pero limpios para LLMs.
* Artefactos trazables en CI/CD.
* Paquetes de revisión de código con números de línea estables.
* Una *fuente de verdad* que puedes incrustar en documentación o bases de conocimiento.

---

## 0 · TL;DR – Guía Rápida

```bash
# 1 ─ Local + remoto: volcar .py + .xml de addons/ y web/, *más* un scrape
#     recursivo (2 niveles) de https://gaheos.com.  Todo en Markdown,
#     enviado a OpenAI y respuesta guardada:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -F https://gaheos.com -d 2 \
         -u markdown \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Dry‑run: listar cada HTML descubierto desde la home
ghconcat -F https://gaheos.com -s .html -l

# 3 ─ Pipeline declarativo multi‑paso con contexts
ghconcat -x conf/pipeline.gcx -o build/artifact.txt
```

---

## Índice

1. [Filosofía](#1--filosofía)
2. [Cobertura de Lenguajes y Formatos](#2--cobertura-de-lenguajes-y-formatos)
3. [Instalación](#3--instalación)
4. [Inicio Rápido](#4--inicio-rápido)
5. [Referencia CLI](#5--referencia-cli)
6. [Modelo Conceptual](#6--modelo-conceptual)
7. [Archivos de Directivas & Contextos](#7--archivos-de-directivas--contextos)
8. [Plantillas & Variables](#8--plantillas--variables)
9. [Pasarela de IA](#9--pasarela-de-ia)
10. [Workspaces & Salidas](#10--workspaces--salidas)
11. [Recetas](#11--recetas)
12. [Ingesta y Scrape de URLs Remotas](#12--ingesta-y-scrape-de-urls-remotas)
13. [Solución de Problemas](#13--solución-de-problemas)
14. [Variables de Entorno & Códigos de Salida](#14--variables-de-entorno--códigos-de-salida)
15. [Guía de Contribución](#15--guía-de-contribución)
16. [Licencia](#16--licencia)

---

## 1 · Filosofía

| Principio                  | Razón de ser                                                                                 |
|----------------------------|----------------------------------------------------------------------------------------------|
| **Determinismo primero**   | Mismo input ⇒ mismo dump – ideal para detectar desvíos en CI.                                |
| **Componible por diseño**  | Mezcla *one‑liners*, archivos de directivas (`‑x`) y contexts jerárquicos en un solo script. |
| **Solo‑lectura & atómico** | Nunca toca tus fuentes; escribe únicamente donde indiques (`‑o`).                            |
| **LLM‑ready**              | Un único flag (`--ai`) conecta el dump con OpenAI.                                           |
| **Cero dependencias**      | Python ≥ 3.8 puro. El puente con OpenAI es opcional (`pip install openai`).                  |

---

## 2 · Cobertura de Lenguajes y Formatos

El mapa de *comment rules* cubre **más de 30 lenguajes y formatos** populares, permitiendo eliminar comentarios e
imports/exports con precisión en un *stack* moderno.

| Tipo / Extensión          | Comentarios soportados                      | Detección de import | Detección de export       |
|---------------------------|---------------------------------------------|---------------------|---------------------------|
| Python `.py`              | `# …`                                       | `import / from`     | —                         |
| JavaScript `.js`          | `// …`, `/* … */`                           | `import`            | `export / module.exports` |
| TypeScript `.ts` / `.tsx` | igual que JS                                | `import`            | `export`                  |
| JSX `.jsx`                | igual que JS                                | `import`            | `export`                  |
| Dart `.dart`              | `// …`, `/* … */`                           | `import`            | `export`                  |
| Go `.go`                  | `// …`, `/* … */`                           | `import`            | —                         |
| …                         | *\[ver lista completa en el código fuente]* |                     |                           |

---

## 3 · Instalación

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
<summary><strong>Opcional – puente OpenAI</strong></summary>

```bash
python3 -m pip install openai
export OPENAI_API_KEY=sk-********************************
```

</details>

---

## 4 · Inicio Rápido

| Objetivo / Tarea                                  | Comando                                                                                  |
|---------------------------------------------------|------------------------------------------------------------------------------------------|
| Concat **.py** en `src/` → `dump.txt`             | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Auditar un **addon Odoo** sin comentarios/imports | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Dry‑run (listado relativo)                        | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Dump `.py + .dart`, envoltura Markdown + OpenAI   | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Artefacto multi‑paso vía contexts                 | `ghconcat -x ci_pipeline.gcx -o build/ci_bundle.txt`                                     |

---

## 5 · Referencia CLI

*Los flags repetibles se marcan con **·***

| Categoría             | Flags & argumentos                          | Descripción                                           |
|-----------------------|---------------------------------------------|-------------------------------------------------------|
| **Discovery**         | `-w DIR` / `-W DIR`                         | Raíz / workspace                                      |
|                       | `-a PATH`· / `-A PATH`·                     | Incluir / excluir ruta local                          |
|                       | `-f URL`·                                   | **Fetch** URL remota (una vez)                        |
|                       | `-F URL`·                                   | **Scrape** recursivo desde URL                        |
|                       | `-d N`, `--url-scrape-depth N`              | Profundidad máx. para `-F` (def.=2, `0`=solo semilla) |
|                       | `-D`, `--disable-same-domain`               | Permite *cross‑domain* durante scrape                 |
|                       | `-s SUF`· / `-S SUF`·                       | Incluir / excluir por sufijo                          |
| **Line slicing**      | `-n NUM`, `-N LINE`, `-m`, `-M`             | Recorte de líneas                                     |
| **Clean‑up**          | `-c`, `-C`, `-i`, `-I`, `-b`, `-B`          | Limpieza de comentarios / imports / blancos           |
| **Template & Output** | `-t FILE`, `-o FILE`, `-u LANG`, `-U`, …    | Render y salida                                       |
| **AI Bridge**         | `--ai`, `--ai-model`, `--ai-temperature`, … | Integración con OpenAI                                |
| **Batching**          | `-x FILE`·                                  | Archivos de directivas con contexts                   |
| **Misc**              | `--upgrade`, `--help`                       | Utilidades                                            |

*Cualquier flag de valor admite `none` para anular herencia.*

---

## 6 · Modelo Conceptual

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

---

## 7 · Archivos de Directivas & Contextos

*(ver ejemplo en la versión en inglés; reglas de herencia idénticas)*

---

## 8 · Plantillas & Variables

*(placeholders `{var}`, alias de contexto, `ghconcat_dump`, etc.)*

---

## 9 · Pasarela de IA

*(mismos parámetros; timeout 1800 s; salida a `_ia_ctx`)*

---

## 10 · Workspaces & Salidas

*(`‑w` y `‑W`; rutas relativas)*

---

## 11 · Recetas

<details>
<summary><strong>11.1 Volcado amigable para <em>code&nbsp;review</em></strong></summary>

```bash
ghconcat -s .py -C -i -a src -o /tmp/base.txt
# …
````

</details>

<details>
<summary><strong>11.2 “Fuente de verdad” Markdown</strong></summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/truth.md
```

</details>

<details>
<summary><strong>11.3 Pipeline con post-proceso IA</strong></summary>

```gcx
# ver ejemplo completo arriba
```

</details>

<details>
<summary><strong>11.4 Paquete remoto + local para revisión</strong></summary>

```bash
ghconcat -a src -s .py \
         -F https://gaheos.com/docs -d 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

---

## 12 · Ingesta y Scrape de URLs Remotas

| Flag                         | Comportamiento                                                                                       |
|------------------------------|------------------------------------------------------------------------------------------------------|
| `-f URL` (fetch)             | Descarga la URL una vez y la trata como archivo local. Extensión inferida si falta.                  |
| `-F URL` (scrape)            | Crawler limitado por profundidad; sigue enlaces `<a href="">` HTML. Enlaces sin extensión ⇒ `.html`. |
| `-d / --url-scrape-depth`    | Profundidad máx. (def. 2, `0` solo la página semilla).                                               |
| `-D / --disable-same-domain` | Permite seguir enlaces hacia otros dominios.                                                         |
| **Logs**                     | Mensajes a *stderr* `✔ fetched …` / `✔ scraped … (d=N)`.                                             |

*Remotos y locales se mezclan sin fricciones: usa `-a`, `-f`, `-F` como quieras.*

---

## 13 · Solución de Problemas

| Síntoma                          | Pista                                            |
|----------------------------------|--------------------------------------------------|
| Dump vacío                       | Revisa `-a/-s` y exclusiones `-A/-S`.            |
| Timeout con ChatGPT              | Red, cuota o prompt > 128 k tokens.              |
| Placeholder sin resolver `{foo}` | Define con `-e foo=bar` o usa alias de contexto. |
| Encabezados duplicados           | No mezcles `-h` internos con template raíz.      |
| `flag expects VAR=VAL`           | Sintaxis incorrecta en `-e` o `-E`.              |
| Imports/exports siguen presentes | Añade `-i` y/o `-I` según el lenguaje.           |
| Demasiados archivos raspados     | Baja `-d` o ajusta filtros `-s / -S`.            |

---

## 14 · Variables de Entorno & Códigos de Salida

| Variable                | Propósito                              |
|-------------------------|----------------------------------------|
| `OPENAI_API_KEY`        | Habilita `--ai`.                       |
| `GHCONCAT_DISABLE_AI=1` | Stub local de IA (tests).              |
| `DEBUG=1`               | Traza completa en errores inesperados. |

| Código | Significado              |
|--------|--------------------------|
| 0      | Éxito                    |
| 1      | Error fatal / validación |
| 130    | Interrumpido por Ctrl‑C  |

---

## 15 · Guía de Contribución

* **Estilo**: `ruff` + `mypy --strict` + perfil *black* por defecto.
* **Tests**: `python -m unittest -v` o `pytest -q`.
* Commits: `feat: add wrap‑U flag` (imperativo, sin punto final).
* Abre un *issue* antes de refactors grandes – ¡PRs bienvenidos!

---

## 16 · Licencia

MIT © GAHEOS S.A.
