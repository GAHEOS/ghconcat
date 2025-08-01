# ghconcat

> **Multi‑language file concatenator with Odoo & Flutter presets, advanced slicing, hierarchical batching and ChatGPT
off‑loading — all in one self‑contained Python script.**

`ghconcat` recorre tu árbol de proyecto, selecciona los ficheros relevantes, **elimina el ruido**, corta por rangos de
líneas y concatena el resultado en un volcado determinista y legible.
Úsalo para revisiones de código, como contexto de un LLM o para generar bundles trazables en CI.

---

## 0 · TL;DR

```bash
# 1 – Resumen de 100 líneas (máx.) de todos los .py y .xml bajo addons/ y web/,
# listo para ChatGPT; respuesta en Markdown:
ghconcat -g py -g xml -C -i -n 100 \
         -a addons -a web \
         -t ai/prompt.tpl            \
         --ai --ai-model o3          \
         -o ai/reply.md

# 2 – El mismo volcado pero **solo los paths**:
ghconcat -g py -g xml -a addons -l

# 3 – “CI bundle” que agrupa tres trabajos independientes:
ghconcat -X conf/ci_backend.gcx \
         -X conf/ci_frontend.gcx \
         -X conf/ci_assets.gcx   \
         -o build/ci_bundle.txt
```

---

## Tabla de contenidos

1. [Filosofía](#1--filosofía)
2. [Matriz de funcionalidades](#2--matriz-de-funcionalidades)
3. [Instalación](#3--instalación)
4. [Guía rápida](#4--guía-rápida)
5. [Referencia CLI completa](#5--referencia-cli-completa)
6. [Modelo conceptual](#6--modelo-conceptual)
7. [Archivos de directivas `‑x` & `‑X`](#7--archivos-de-directivas-x--x)
8. [Recetas](#8--recetas)
9. [Pasarela ChatGPT](#9--pasarela-chatgpt)
10. [Autoactualización](#10--autoactualización)
11. [Variables de entorno y códigos de salida](#11--variables-de-entorno-y-códigos-de-salida)
12. [Solución de problemas](#12--solución-de-problemas)
13. [FAQ](#13--faq)
14. [Contribuir](#14--contribuir)
15. [Licencia](#15--licencia)

---

## 1 · Filosofía

| Principio                   | Motivo                                                         |
|-----------------------------|----------------------------------------------------------------|
| **Un solo comando**         | No más abrir docenas de archivos para entender un PR           |
| **Salida determinista**     | Mismo input ⇒ mismo output → perfect match en CI               |
| **Orquestación componible** | Bundles `‑x`, lotes jerárquicos `‑X`, herencia controlada      |
| **Sólo lectura**            | Nunca re‑escribe tu fuente; todo ocurre en RAM                 |
| **Flujo AI‑first**          | Puente integrado `--ai` con prompt de sistema y semillas JSONL |

---

## 2 · Matriz de funcionalidades

| Dominio                | Destacados                                                                                                       |
|------------------------|------------------------------------------------------------------------------------------------------------------|
| **Descubrimiento**     | Recorrido recursivo, exclusiones de ruta/dir, filtro por sufijo, **ignora ocultos y .g.dart**                    |
| **Juego de lenguajes** | Inclusiones `‑g` y exclusiones `‑G`; presets `odoo`, `flutter`, combinables                                      |
| **Limpieza**           | Elimina comentarios simples `‑c` o todos `‑C`, imports `‑i`, exports `‑I`, líneas en blanco (`‑B` opcional)      |
| **Corte**              | Mantén *n* líneas (`‑n`), inicio arbitrario (`‑N`), conserva cabecera (`‑H`)                                     |
| **Batching**           | Bundles `‑x` (prioridad 1) y contextos `‑X` (niveles > 1) con reglas de herencia y desactivación `none`          |
| **Plantillas**         | Placeholder `{dump_data}`, aliases `‑O`, variables de entorno locales `‑e` y globales `‑E`                       |
| **LLM Bridge**         | ChatGPT con timeout 1800 s, semillas `--ai-seeds`, re‑interpolación post‑IA, alias sobre‑escrito                 |
| **Salida**             | Archivo opcional `‑o` o retorno directo por API, cabecera relativa (default) o absoluta `‑p`, sin cabeceras `‑P` |
| **Auto‑upgrade**       | `--upgrade` descarga la última versión estable en un paso                                                        |

---

## 3 · Instalación

> Requiere Python ≥ 3.8.
> La integración con ChatGPT es opcional (`pip install openai`).

### Linux / macOS

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 setup.py install     # o pip install .
mkdir -p ~/.bin && cp ghconcat.py ~/.bin/ghconcat && chmod +x ~/.bin/ghconcat
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat -h
```

### Windows (PowerShell)

```powershell
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python setup.py install
$bin="$env:USERPROFILE\bin"; mkdir $bin -ea 0
copy ghconcat.py "$bin\ghconcat.py"
[Environment]::SetEnvironmentVariable('Path', "$bin;$env:Path", 'User')
Set-Alias ghconcat python "$bin\ghconcat.py"
ghconcat -h
```

### Activar pasarela ChatGPT

```bash
pip install openai
export OPENAI_API_KEY=sk-********************************
```

---

## 4 · Guía rápida

| Tarea                                                                        | Comando                                                                          |
|------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| Volcar todos los **.py** de `src/` a `dump.txt`                              | `ghconcat -g py -a src -o dump.txt`                                              |
| Auditar un **addon Odoo**, quitar comentarios e imports, primeras 100 líneas | `ghconcat -g odoo -C -i -n 100 -a addons/sale_extended`                          |
| Dry‑run (*solo paths*)                                                       | `ghconcat -g odoo -a addons/sale_extended -l`                                    |
| Enviar dump comprimido a ChatGPT con plantilla, guardar respuesta            | `ghconcat -g py -g dart -C -i -a src -t tpl/prompt.md --ai -o reply.md`          |
| Agrupar tres lotes independientes                                            | `ghconcat -X ci_backend.gcx -X ci_frontend.gcx -X ci_assets.gcx -o build/ci.txt` |

---

## 5 · Referencia CLI completa

| Categoría               | Flags (repetibles marcadas ·)                                                       | Descripción resumida                          |
|-------------------------|-------------------------------------------------------------------------------------|-----------------------------------------------|
| **Batch & niveles**     | `‑x FILE`·                                                                          | Carga flags de FILE (prioridad 1)             |
|                         | `‑X FILE`·                                                                          | Ejecuta lote en nuevo contexto (nivel > 1)    |
| **Ubicación**           | `‑w DIR`                                                                            | Workdir/base para paths relativos             |
|                         | `‑W DIR`                                                                            | Workspace para plantillas, prompts y salidas  |
| **Descubrimiento**      | `‑a PATH`·                                                                          | Añadir archivo/directorio                     |
|                         | `‑A PATH`·                                                                          | Excluir archivo/directorio                    |
|                         | `‑s SUF`· / `‑S SUF`·                                                               | Incluir / excluir por sufijo                  |
| **Lenguajes**           | `‑g LANG`· / `‑G LANG`·                                                             | Incluir / excluir extensión o preset          |
| **Slicing**             | `‑n NUM`, `‑N LINE`, `‑H`                                                           | Líneas totales, inicio, conservar cabecera    |
| **Limpieza**            | `‑c`, `‑C`, `‑i`, `‑I`, `‑B`                                                        | Comentarios, imports, exports, lineas blancas |
| **Plantillas & output** | `‑t FILE` (o `‑t none`)                                                             | Plantilla; `none` desactiva herencia          |
|                         | `‑o FILE`                                                                           | Archivo de salida                             |
|                         | `‑O ALIAS`                                                                          | Alias para exportar dump/render/IA            |
|                         | `‑u LANG` (o `‑u none`)                                                             | Wrap Markdown `LANG`                          |
|                         | `‑l`, `‑p`, `‑P`                                                                    | Sólo paths, cabecera absoluta, sin cabeceras  |
| **Variables**           | `‑e VAR=VAL`·                                                                       | Variable local al contexto                    |
|                         | `‑E VAR=VAL`·                                                                       | Variable global (se propaga)                  |
| **Gateway IA**          | `--ai`                                                                              | Activa ChatGPT                                |
|                         | `--ai-model M`                                                                      | Modelo (def. o3)                              |
|                         | `--ai-system-prompt FILE`                                                           | Prompt de sistema                             |
|                         | `--ai-seeds FILE/none`                                                              | Seeds JSONL heredables                        |
|                         | `--ai-temperature`, `--ai-top-p`, `--ai-presence-penalty`, `--ai-frequency-penalty` | Parámetros opcionales                         |
| **Otros**               | `--upgrade`                                                                         | Auto‑actualización                            |
|                         | `-h`                                                                                | Ayuda                                         |

> *Cualquier flag “de valor” admite `none` para cancelar la herencia en el contexto actual.*

---

## 6 · Modelo conceptual

```
roots (-a) ─▶ filtros ruta/sufijo ─▶ set lenguajes ─▶ limpieza ─▶ slicing ─▶ dump
            (‑A,‑s,‑S)              (‑g/‑G)             (‑c/‑C,‑i/‑I,‑B)    (‑n/‑N)
                                                          │
                                                          ▼
                                    templating (‑t) ─▶ ChatGPT (--ai) ─▶ output (‑o / alias)
```

---

## 7 · Archivos de directivas `‑x` & `‑X`

### 7.1 `‑x` – Bundles de flags (nivel 1)

* Se expanden **antes** del parseo CLI.
* Múltiples `‑x` se concatenan en orden; la CLI puede sobrescribirlos.

```gcx
# defaults.gcx
-g odoo
-c -i -n 120
-a addons -a tests
```

```bash
ghconcat -x defaults.gcx -G js -a docs -o dump.txt
```

### 7.2 `‑X` – Lotes jerárquicos (niveles > 1)

* Cada línea del archivo se tokeniza igual que la CLI.
* Heredan flags y variables del nivel superior según reglas:

| Tipo de atributo | Herencia                    |
|------------------|-----------------------------|
| Booleanos        | OR (no pueden des‑setear)   |
| Listas           | Se concatenan               |
| Escalares        | Hijo sobreescribe si define |
| No heredados     | `‑o`, `‑O`, `--ai`, `‑t`    |

* Los nombres `[alias]` dentro de un `.gcx` crean sub‑contextos sin archivo externo (equivalen a `‑X __ctx:alias`).

---

## 8 · Recetas

<details>
<summary><strong>8.1 Diff human‑friendly en CI</strong></summary>

```bash
# master
ghconcat -g odoo -C -i -a addons/sale -o /tmp/base.txt

# feature branch
ghconcat -g odoo -C -i -a addons/sale -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>8.2 Cabeceras absolutas para enlaces HTML</strong></summary>

```bash
ghconcat -g py -g xml -C -i -a src -p -u text -o build/audit.txt
```

</details>

<details>
<summary><strong>8.3 Resumen arquitectónico automático (ChatGPT)</strong></summary>

```bash
ghconcat -g py -g dart -C -i -a src \
         -t ai/summarise.tpl \
         -e version=$(git rev-parse --short HEAD) \
         --ai --ai-model o3 \
         -o ai/summary.md
```

</details>

<details>
<summary><strong>8.4 Bundle CI con tres contextos</strong></summary>

```bash
ghconcat -X ci_backend.gcx -X ci_frontend.gcx -X ci_assets.gcx -o build/ci_bundle.txt
```

</details>

---

## 9 · Pasarela ChatGPT

| Aspecto          | Detalle                                                                               |
|------------------|---------------------------------------------------------------------------------------|
| Prompt sistema   | `--ai-system-prompt`; se interpola con variables/alias                                |
| Placeholders     | Siempre `{dump_data}` + variables `‑e/‑E` y alias `‑O`                                |
| Seeds            | JSONL por línea (`--ai-seeds file.jsonl`), heredables; `none` para desactivar         |
| Tiempo máximo    | 1800 s                                                                                |
| Seguridad tokens | Corta con error si el prompt supera ≈ 128 k tokens                                    |
| Resultado        | Respuesta se guarda en `‑o` o en archivo temporal; el alias se actualiza con el texto |

---

## 10 · Auto‑actualización

```bash
ghconcat --upgrade      # copia la última versión estable a ~/.bin/ghconcat
```

Programa en `crontab`:

```
0 6 * * MON ghconcat --upgrade >/var/log/ghconcat-up.log 2>&1
```

---

## 11 · Variables de entorno y códigos de salida

| Variable         | Efecto                                |
|------------------|---------------------------------------|
| `OPENAI_API_KEY` | Habilita `--ai`                       |
| `DEBUG=1`        | Muestra traceback completo en errores |

| Código | Significado                   |
|--------|-------------------------------|
| 0      | Éxito                         |
| 1      | Error fatal / validación      |
| 130    | Interrupción por usuario (^C) |

---

## 12 · Solución de problemas

| Síntoma                                               | Corrección                                             |
|-------------------------------------------------------|--------------------------------------------------------|
| “after apply all filters no active extension remains” | Revisa combinación `‑g/‑G`; filtraste todo             |
| Dump vacío / faltan archivos                          | Comprueba rutas `‑a`, sufijos `‑s/‑S`, dirs ocultos    |
| ChatGPT cuelga                                        | Clave API, red, tamaño prompt < 128 k tokens           |
| “flag expects VAR=VAL”                                | Formato incorrecto en `‑e` o `‑E`                      |
| Seeds JSON mal formateados                            | Cada línea debe ser JSON válido con `role` y `content` |

---

## 13 · FAQ

<details>
<summary>¿Puedo anidar `‑X` dentro de otro `‑X`?</summary>
No. Evitamos recursión accidental; usa varios `‑X` de nivel 0.
</details>

<details>
<summary>¿Por qué se ignoran los archivos <code>*.g.dart</code>?</summary>
Son generados; reduce ruido. Usa `‑s` / `‑S` si quieres incluirlos.
</details>

<details>
<summary>¿Funciona en Windows?</summary>
Sí; es Python puro. Usa los pasos de instalación para PowerShell.
</details>

---

## 14 · Contribuir

* Estilo: **PEP 8**, `ruff`, `mypy --strict`
* Tests: `pytest -q` o `python -m unittest -v`
* Commits: `<scope>: <subject>` (imperativo, sin punto final)
* Firma: `git config --global user.signingkey …`

¡PRs bienvenidos!

---

## 15 · Licencia

**MIT** – ver `LICENSE` para el texto completo.
