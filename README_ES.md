# ghconcat

> **Concatena archivos multi‑lenguaje con batching jerárquico, corte por rangos, limpieza avanzada,
> pasarela OpenAI y total determinismo — todo en un único script Python puro.**

`ghconcat` recorre tu árbol de proyecto, selecciona solo los archivos relevantes, **elimina el ruido**, corta
(opcionalmente) por rango de líneas y concatena todo en un único volcado reproducible.  
Ese volcado sirve para *diffs* de *code‑review*, ventanas de contexto XXL para LLMs, alimentación de herramientas
de análisis estático o generación de artefactos trazables en CI.

---

## 0 · TL;DR – Chuleta rápida

```bash
# 1 ─ Resumen de 100 líneas de cada .py y .xml en addons/ y web/, envuelto en Markdown,
#     enviado a OpenAI y guardado en ai/reply.md:
ghconcat -g py -g xml -C -i -n 100 \
         -a addons -a web \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Mismos criterios de búsqueda, pero solo **listar paths** (dry‑run):
ghconcat -g py -g xml -a addons -l

# 3 ─ “CI bundle” que enlaza tres trabajos independientes:
ghconcat -X conf/ci_backend.gcx \
         -X conf/ci_frontend.gcx \
         -X conf/ci_assets.gcx \
         -o build/ci_bundle.txt
````

---

## Tabla de contenidos

1. [Filosofía](#1--filosofía)
2. [Matriz de funcionalidades](#2--matriz-de-funcionalidades)
3. [Instalación](#3--instalación)
4. [Guía rápida](#4--guía-rápida)
5. [Referencia completa de CLI](#5--referencia-completa-de-cli)
6. [Modelo conceptual](#6--modelo-conceptual)
7. [Archivos de directivas `‑x` & `‑X`](#7--archivos-de-directivas-x--x)
8. [Plantillas y variables](#8--plantillas-y-variables)
9. [Pasarela ChatGPT](#9--pasarela-chatgpt)
10. [Batching y contextos jerárquicos](#10--batching-y-contextos-jerárquicos)
11. [Estrategias de salida & envoltorio Markdown](#11--estrategias-de-salida--envoltorio-markdown)
12. [Gestión de rutas & cabeceras](#12--gestión-de-rutas--cabeceras)
13. [Variables de entorno & códigos de salida](#13--variables-de-entorno--códigos-de-salida)
14. [Auto‑upgrade & fijación de versión](#14--autoupgrade--fijación-de-versión)
15. [Solución de problemas](#15--solución-de-problemas)
16. [Recetas](#16--recetas)
17. [Seguridad & privacidad](#17--seguridad--privacidad)
18. [Rendimiento](#18--rendimiento)
19. [Guía de contribución](#19--guía-de-contribución)
20. [Licencia](#20--licencia)

---

## 1 · Filosofía

| Principio                       | Motivo                                                                                                       |
|---------------------------------|--------------------------------------------------------------------------------------------------------------|
| **Contexto en un solo comando** | No más abrir decenas de archivos para entender un PR: el volcado es legible y con números de línea estables. |
| **Salida determinista**         | Mismo input ⇒ mismo dump. Ideal para *diffs* de CI y *caching*.                                              |
| **Orquestación componible**     | Combina *one‑liners*, bundles inline (`‑x`) y trabajos jerárquicos (`‑X`) sin sacrificar claridad.           |
| **Sólo‑lectura**                | Nunca escribe sobre tu fuente; todo ocurre en memoria o en el `‑o` que indiques.                             |
| **Flujo AI‑first**              | Puente con OpenAI: *seeds* JSONL, *system prompts*, interpolación de alias y control de *timeout*.           |
| **Sin dependencias externas**   | Python ≥ 3.8; la puerta a ChatGPT es opcional (`pip install openai`).                                        |
| **Multiplataforma**             | Linux, macOS, Windows (PowerShell) — sin extensiones nativas ni trucos de *shell*.                           |

---

## 2 · Matriz de funcionalidades

| Dominio                 | Destacados                                                                                                                                  |
|-------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| **Descubrimiento**      | Recorrido recursivo, inclusión/exclusión de rutas, filtro por sufijo, ignora ocultos, omite `*.g.dart`, de‑dup de cabeceras entre contextos |
| **Presets de lenguaje** | `odoo`, `flutter`, además de extensiones arbitrarias y mezclas (`‑g py -g xml -g .csv`).                                                    |
| **Limpieza**            | Elimina comentarios simples (`‑c`) o todos (`‑C`), imports (`‑i`), exports (`‑I`), líneas en blanco opcionales (por defecto las quita).     |
| **Corte**               | Primeras *n* líneas (`‑n`), inicio arbitrario (`‑N`), conserva línea 1 aunque se corte (`‑H`).                                              |
| **Batching**            | Bundles inline (`‑x`) y trabajos jerárquicos (`‑X`); herencia OR/concat, `none` para anular flags aguas arriba.                             |
| **Plantillas**          | Placeholder `{dump_data}`, aliases ilimitados (`‑O`), variables locales (`‑e`) y globales (`‑E`), *workspace* y sustitución `$ENV_VAR`.     |
| **Puente LLM**          | Modelos OpenAI, *timeout* 1800 s, seeds JSONL, fences automáticos (`‑u lang`), corte duro a ≈128 k tokens.                                  |
| **Salida**              | `‑o` opcional, dry‑run (`‑l`), cabeceras absolutas/relativas (`‑p`), modo sin cabecera (`‑P`), envoltorio Markdown (`‑u`).                  |
| **Auto‑upgrade**        | `--upgrade` atómico: clona la última versión a `~/.bin/ghconcat` y la hace ejecutable.                                                      |

---

## 3 · Instalación

> Requiere **Python 3.8+**. La pasarela ChatGPT es opcional.

### Linux / macOS

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 setup.py install     # o: pip install .
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat -h
```

### Activar pasarela ChatGPT

```bash
pip install openai
export OPENAI_API_KEY=sk-********************************
```

---

## 4 · Guía rápida

| Tarea                                                                        | Comando                                                                                                                  |
|------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Volcar todos los **.py** de `src/` en `dump.txt`                             | `ghconcat -g py -a src -o dump.txt`                                                                                      |
| Auditar un **addon Odoo**, quitar comentarios e imports, primeras 100 líneas | `ghconcat -g odoo -C -i -n 100 -a addons/sale_extended`                                                                  |
| Dry‑run (solo paths)                                                         | `ghconcat -g odoo -a addons/sale_extended -l`                                                                            |
| Enviar dump comprimido a ChatGPT con plantilla y guardar respuesta           | `ghconcat -g py -g dart -C -i -a src -t tpl/prompt.md --ai -o reply.md`                                                  |
| Unir tres trabajos por lotes                                                 | `ghconcat -X ci_backend.gcx -X ci_frontend.gcx -X ci_assets.gcx -o build/ci.txt`                                         |
| Envolver cada chunk en fences Markdown `js`                                  | `ghconcat -g js -u js -a web -o docs/src_of_truth.md`                                                                    |
| Resumen arquitectónico con hash de commit                                    | `ghconcat -g py -g dart -C -i -a src -t ai/summarise.tpl -e version=$(git rev-parse --short HEAD) --ai -o ai/summary.md` |

---

## 5 · Referencia completa de CLI

Los flags repetibles llevan **·**.

| Categoría               | Flags & parámetros                                                                                    | Descripción                                                           |
|-------------------------|-------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **Batch / nesting**     | `‑x FILE`·                                                                                            | Bundle inline — se expande antes del parseo.                          |
|                         | `‑X FILE`·                                                                                            | Contexto jerárquico — se hereda (ver §10).                            |
| **Ubicación**           | `‑w DIR`                                                                                              | Workdir / raíz de paths relativos (def.=CWD).                         |
|                         | `‑W DIR`                                                                                              | Workspace para plantillas, prompts y salidas (def.=workdir).          |
|                         | `‑a PATH`·                                                                                            | Añadir archivo o directorio.                                          |
|                         | `‑A PATH`·                                                                                            | Excluir archivo/directorio (prefijo).                                 |
|                         | `‑s SUF`· / `‑S SUF`·                                                                                 | Incluir / excluir por sufijo.                                         |
| **Filtros de lenguaje** | `‑g LANG`· / `‑G LANG`·                                                                               | Incluir / excluir extensión o preset (`odoo`, `flutter`).             |
| **Rango de líneas**     | `‑n NUM`                                                                                              | Mantener como máximo NUM líneas.                                      |
|                         | `‑N LINE`                                                                                             | Línea inicial 1‑based (con o sin `‑n`).                               |
|                         | `‑H`                                                                                                  | Duplicar línea 1 original si quedara fuera.                           |
| **Limpieza**            | `‑c` / `‑C`                                                                                           | Quitar comentarios simples / todos.                                   |
|                         | `‑i` / `‑I`                                                                                           | Eliminar import / export.                                             |
|                         | `‑B`                                                                                                  | Conservar líneas en blanco (por defecto se quitan).                   |
| **Salida & plantillas** | `‑t FILE` / `‑t none`                                                                                 | Plantilla con `{dump_data}`; `none` anula la heredada.                |
|                         | `‑o FILE`                                                                                             | Archivo de salida final.                                              |
|                         | `‑O ALIAS`                                                                                            | Expone dump/render como `${ALIAS}` a padres/plantillas.               |
|                         | `‑u LANG` / `‑u none`                                                                                 | Envolver cada chunk en `LANG`; `none` elimina el envoltorio heredado. |
|                         | `‑l`                                                                                                  | Solo lista paths.                                                     |
|                         | `‑p` / `‑P`                                                                                           | Cabeceras absolutas / sin cabeceras.                                  |
| **Variables**           | `‑e VAR=VAL`·                                                                                         | Variable local (solo contexto actual).                                |
|                         | `‑E VAR=VAL`·                                                                                         | Variable global (se propaga a hijos).                                 |
| **Pasarela AI**         | `--ai`                                                                                                | Activa llamada a ChatGPT.                                             |
|                         | `--ai-model M`                                                                                        | Modelo OpenAI (def. `o3`).                                            |
|                         | `--ai-system-prompt FILE`                                                                             | Prompt de sistema propio (con plantillas).                            |
|                         | `--ai-seeds FILE/none`                                                                                | Seeds JSONL; `none` anula herencia.                                   |
|                         | Parámetros extra: `--ai-temperature`, `--ai-top-p`, `--ai-presence-penalty`, `--ai-frequency-penalty` |                                                                       |
| **Miscelánea**          | `--upgrade`                                                                                           | Auto‑upgrade desde GitHub.                                            |
|                         | `-h`                                                                                                  | Ayuda.                                                                |

> *Cualquier flag de valor puede anularse en un hijo con `none`.*

---

## 6 · Modelo conceptual

```
roots (‑a)  →  filtros ruta/sufijo (‑A/‑s/‑S) → set de lenguajes (‑g/‑G) → limpieza → corte → dump
                                                                                 │
                                                                                 ▼
                                      plantillas (‑t) → ChatGPT (--ai) → salida (‑o / alias)
```

---

## 7 · Archivos de directivas `‑x` & `‑X`

### 7.1 Bundles inline `‑x`

* Se parsean **antes** de `argparse`; pueden añadir o sobreescribir flags.
* Varios `‑x` se concatenan en orden.

```gcx
# defaults.gcx
-g odoo
-c -i -n 120
-a addons -a tests
```

```bash
ghconcat -x defaults.gcx -G js -a docs -o dump.txt
```

### 7.2 Contextos jerárquicos `‑X`

* Cada línea se tokeniza igual que la CLI.
* Herencia:

| Tipo de atributo | Regla de fusión                     |
|------------------|-------------------------------------|
| Booleanos        | **OR** lógico (no se pueden quitar) |
| Listas           | Padre + Hijo (concat)               |
| Escalares        | El hijo sobrescribe                 |
| No heredados     | `‑o`, `‑O`, `--ai`, `‑t`            |

* `[alias]` dentro de `.gcx` crea un subcontexto inline igual que `‑X __ctx:alias`.

---

## 8 · Plantillas y variables

* Placeholder siempre disponible: **`{dump_data}`**.
* Cada `‑O ALIAS` añade `{ALIAS}` aguas abajo.
* Variables `‑e` / `‑E`; pueden usarse como `$VAR` dentro de directivas.
* Resolución de plantillas: primero `--workspace`, luego `--workdir`.

---

## 9 · Pasarela ChatGPT

| Aspecto           | Detalle                                                                                              |
|-------------------|------------------------------------------------------------------------------------------------------|
| Activación        | Flag `--ai`; necesita `OPENAI_API_KEY`.                                                              |
| Prompt sistema    | `--ai-system-prompt FILE`, compatible con plantillas.                                                |
| Seeds             | JSONL (`role` + `content`); heredado salvo `--ai-seeds none`.                                        |
| Timeout           | 1800 s.                                                                                              |
| Corte de tokens   | Límite ≈128 k tokens (≈350 k chars) para evitar error 413.                                           |
| Parámetros modelo | Temp, top‑p, presence y frequency (ignorados en modelos de temp fija como `o3`).                     |
| Manejo de salida  | Si hay `‑o`, la respuesta se escribe ahí; si no, a un temp; alias se actualiza **después** de la IA. |
| Errores           | Fallos de red/cupo/parseo → exit distinto de 0; dump original intacto.                               |

---

## 10 · Batching y contextos jerárquicos

* Se permiten infinitos `‑X` a nivel 0; anidar más de un nivel está **prohibido** (evita recursión).
* De‑duplicación global de cabeceras automática cuando **no** hay plantilla a nivel 0.
* Cada hijo puede usar ChatGPT, su propia plantilla o sobrescribir variables.

---

## 11 · Estrategias de salida & envoltorio Markdown

* Cabeceras **relativas** (defecto) ideales para *diffs*.
* `‑p` genera cabeceras absolutas (útil para HTML con enlaces).
* `‑u LANG` envuelve cada chunk en fences `LANG`.
* `‑l` + `‑p` produce un manifiesto de paths absolutos.
* `‑P` elimina cabeceras (si una plantilla ya las incluye).

---

## 12 · Gestión de rutas & cabeceras

* Ocultos (`.foo`, `.git`, `.private`) se ignoran salvo inclusión explícita.
* `*.g.dart` se omite por defecto.
* `‑H` duplica línea 1 solo si quedaría fuera por el corte.
* `none` desactiva flags heredados (`‑n none`, `‑u none`, etc.).

---

## 13 · Variables de entorno & códigos de salida

| Variable         | Función                                |
|------------------|----------------------------------------|
| `OPENAI_API_KEY` | Activa `--ai`.                         |
| `DEBUG=1`        | Muestra trazas de Python ante errores. |

| Código | Significado                         |
|--------|-------------------------------------|
| 0      | Éxito                               |
| 1      | Error fatal / validación            |
| 130    | Interrupción por usuario (`Ctrl‑C`) |

---

## 14 · Auto‑upgrade & fijación de versión

```bash
ghconcat --upgrade
```

Clona la versión estable a `~/.bin/ghconcat` y la marca como ejecutable.
En `cron`:

```
0 6 * * MON ghconcat --upgrade >/var/log/ghconcat-up.log 2>&1
```

Para builds herméticos, exporta `GHCONCAT_VERSION` y verifícalo en tu CI.

---

## 15 · Solución de problemas

| Síntoma                                                 | Corrección                                                   |
|---------------------------------------------------------|--------------------------------------------------------------|
| *“after apply all filters no active extension remains”* | Ajusta la mezcla `‑g`/`‑G`; filtraste todo.                  |
| Dump vacío / faltan archivos                            | Revisa raíces (`‑a`), sufijos (`‑s`/`‑S`), carpetas ocultas. |
| ChatGPT “se cuelga” o expira                            | ¿Red? ¿API key? ¿Prompt <128 k tokens?                       |
| “flag expects VAR=VAL”                                  | Revisa sintaxis de `‑e` / `‑E`.                              |
| Seeds ignoradas tras `--ai-seeds none`                  | Comportamiento normal: herencia anulada.                     |
| Cabeceras duplicadas                                    | Usa plantillas **o** de‑dupe global, no los dos a la vez.    |

---

## 16 · Recetas

<details>
<summary><strong>16.1 Dump amigable para *diff* en code‑review</strong></summary>

```bash
# rama principal
ghconcat -g odoo -C -i -a addons/sale -o /tmp/base.txt

# rama feature (checkout primero)
ghconcat -g odoo -C -i -a addons/sale -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>16.2 Auditoría con paths absolutos en CI</strong></summary>

```bash
ghconcat -g py -g xml -C -i -a src -p -u text -o build/audit.txt
```

Convierte `audit.txt` a HTML enlazando con tu navegador de repositorio.

</details>

<details>
<summary><strong>16.3 Hook pre‑commit: lint + dump de archivos staged</strong></summary>

```bash
#!/usr/bin/env bash
changed=$(git diff --cached --name-only --relative | tr '\n' ' ')
[ -z "$changed" ] && exit 0

ruff $changed && mypy --strict $changed || exit 1

ghconcat -g py -C -i -a $changed -o /tmp/pre_commit_dump.txt
less /tmp/pre_commit_dump.txt
```

</details>

<details>
<summary><strong>16.4 “Fuente de la verdad” Markdown en un comando</strong></summary>

```bash
ghconcat -g dart -g js -C -i -a lib -a web -u js -o docs/source_of_truth.md
```

</details>

<details>
<summary><strong>16.5 Resumen OpenAPI con seeds</strong></summary>

```bash
ghconcat -g yml -g yaml -C -a api \
         -t ai/openapi.tpl \
         --ai --ai-seeds ai/seeds.jsonl \
         -o ai/openapi_overview.md
```

</details>

<details>
<summary><strong>16.6 Bundle de backend, frontend y assets</strong></summary>

```bash
ghconcat -X ci_backend.gcx \
         -X ci_frontend.gcx \
         -X ci_assets.gcx \
         -o build/ci_bundle.txt
```

</details>

---

## 17 · Seguridad & privacidad

* El código **no** sale de tu máquina salvo que actives `--ai`.
* Con `--ai`, **todo** el prompt se envía a OpenAI. Evalúa tu política de IP.
* `OPENAI_API_KEY` solo se lee en runtime; no se cachea localmente.
* En CI, bloquea egress si necesitas impedir llamadas externas.
* Si el prompt excede el límite, `ghconcat` aborta con mensaje claro.

---

## 18 · Rendimiento

* Combina `‑c` e `‑i` para recortar ≈35% de tokens en repos Python.
* Usa presets (`-g odoo`) en lugar de muchas extensiones sueltas.
* En contenedores, monta `‑W` en tmpfs para I/O más rápido.
* Agrupa archivos lógicamente en `‑X` para maximizar de‑dupe de cabeceras.

---

## 19 · Guía de contribución

1. **Estilo** `ruff` + `mypy --strict` + *black* por defecto.
2. **Tests** `pytest -q` o `python -m unittest -v`.
3. **Commits** `<scope>: <subject>` (imperativo, sin punto final).
4. **Sign‑off** `git config --global user.signingkey …`.
5. **PRs** ¡bienvenidos! Abre issue antes de refactors grandes.

---

## 20 · Licencia

**MIT** — consulta `LICENSE` para el texto completo.

