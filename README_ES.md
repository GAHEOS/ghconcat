# ghconcat

> **Concatenador multilenguaje con presets para Odoo / Flutter, recorte avanzado, orquestación por lotes y envío directo a ChatGPT.**

`ghconcat` reúne, limpia y concatena archivos fuente heterogéneos—Python, Dart, XML, CSV, JS, YAML, lo que necesites—en un único volcado ordenado. Ese volcado puede leerse cómodamente, compararse en CI o enviarse a ChatGPT para revisiones y refactorizaciones automatizadas.

---

## Índice

1. [Filosofía](#1--filosofía)
2. [Matriz de funcionalidades](#2--matriz-de-funcionalidades)
3. [Instalación](#3--instalación)
4. [Primeros pasos](#4--primeros-pasos)
5. [Referencia CLI completa](#5--referencia-cli-completa)
6. [Modelo conceptual](#6--modelo-conceptual)
7. [Profundizando en ficheros de directivas (`-x` y `-X`)](#7--profundizando-en-ficheros-de-directivas)
   1. [7.1 Inline (`-x`) – Paquetes de flags](#71-inline-x--paquetes-de-flags)
   2. [7.2 Batch (`-X`) – Trabajos independientes](#72-batch-x--trabajos-independientes)
8. [Recetas y flujos de trabajo](#8--recetas-y-flujos-de-trabajo)
   1. [8.1 Diff “narrativo” para revisión](#81-diff-narrativo-para-revisión)
   2. [8.2 Compresión previa a LLM + resumen](#82-compresión-previa-a-llm--resumen)
9. [Integración con ChatGPT](#9--integración-con-chatgpt)
10. [Proceso de actualización](#10--proceso-de-actualización)
11. [Variables de entorno y códigos de salida](#11--variables-de-entorno-y-códigos-de-salida)
12. [Solución de problemas](#12--solución-de-problemas)
13. [Preguntas frecuentes](#13--preguntas-frecuentes)
14. [Contribuir](#14--contribuir)
15. [Licencia](#15--licencia)


---

## 1 · Filosofía

* **Contexto con un solo comando** Pon fin a la búsqueda de fragmentos en back‑end, front‑end y datos.
* **Determinista por diseño** Salidas idénticas byte por byte → ideales para revisiones de código y diffs en CI.
* **Orquestación componible** Directivas inline/lote + herencia de flags para automatizar trabajos complejos.
* **Ruido cero** Cada limpieza es explícita; tu código nunca se modifica in‑place.
* **Listo para IA** Una pasarela dedicada envía el dump a ChatGPT siguiendo un prompt robusto.

---

## 2 · Matriz de funcionalidades

| Área                  | Capacidades                                                                                                |
| --------------------- |------------------------------------------------------------------------------------------------------------|
| Descubrimiento        | Recorrido recursivo, exclusión por ruta, listas negras de directorios, filtros por sufijo                  |
| Extensiones           | Inclusión (`--py`, `--xml`, …) y exclusión (`--no-*`), más presets (`--odoo`)                              |
| Limpieza              | Eliminar comentarios (`-c` / `-C`), imports (`-i`), exports (`-I`), líneas en blanco (`-S`)                |
| Recorte               | Cabeza/cola (`‑n`), rangos arbitrarios (`‑n` + `‑N`), preservación de cabecera (`‑H`)                      |
| Ficheros de directiva | *Inline* `‑x` (paquetes de flags) y *batch* `‑X` (múltiples trabajos, herencia jerárquica)                 |
| Internacionalización  | Mensajes CLI y prompt de ChatGPT en **inglés** o **español** (`‑l`)                                        |
| Envío a IA            | Inyección de prompt mediante plantilla, captura de respuesta, timeout de 120 s, manejo elegante de errores |
| Mantenimiento         | Auto‑upgrade desde GitHub (`--upgrade`), tracebacks ocultos salvo `DEBUG=1`                                |

---

## 3 · Instalación

### Sistemas Unix‑like

```bash
git clone https://github.com/GAHEOS/ghconcat.git
sudo cp ghconcat/ghconcat.py /usr/local/bin/ghconcat    # o cualquier dir en $PATH
sudo chmod +x /usr/local/bin/ghconcat
ghconcat -h
```

### Windows (PowerShell)

```powershell
git clone https://github.com/GAHEOS/ghconcat.git
Copy-Item ghconcat/ghconcat.py $env:USERPROFILE\bin\ghconcat.py
Set-Alias ghconcat python $env:USERPROFILE\bin\ghconcat.py
ghconcat -h
```

> **Opcional (IA)**
>
> ```bash
> pip install openai
> export OPENAI_API_KEY=sk-********************************
> ```

---

## 4 · Primeros pasos

Concatena **todos** los archivos Python bajo `src/` en `dump.txt`:

```bash
ghconcat --py -a src -f dump.txt
```

Audita un add‑on de Odoo, elimina **todos** los comentarios e imports y conserva solo las primeras 100 líneas:

```bash
ghconcat --odoo -C -i -n 100 -a addons/sale_extended
```

Dry‑run (solo listar los archivos que se concatenarían):

```bash
ghconcat --odoo -t -a addons/sale_extended
```

---

## 5 · Referencia CLI completa

| Corto | Largo / Grupo              | Tipo | Valor por defecto | Descripción                                                       | Ejemplo                    |
| ----- | -------------------------- | ---- | ----------------- | ----------------------------------------------------------------- | -------------------------- |
| `-x`  | — *Pre‑procesado*          | FILE | —                 | Carga flags extra desde FILE **antes** del parseo normal.         | `-x defaults.dct`          |
| `-X`  | — *Pre‑procesado*          | FILE | —                 | Ejecuta un lote independiente definido en FILE y fusiona su dump. | `-X nightly.bat`           |
| `-a`  | — *Filtro*                 | PATH | `.`               | Añade archivo/directorio a las raíces de búsqueda (repetible).    | `-a src -a tests`          |
| `-r`  | `--root`                   | DIR  | CWD               | Directorio base para resolver rutas relativas.                    | `-r /opt/proyecto`         |
| `-e`  | — *Filtro*                 | PAT  | —                 | Excluye rutas que contengan PAT.                                  | `-e .git`                  |
| `-E`  | — *Filtro*                 | DIR  | —                 | Excluye recursivamente el directorio DIR.                         | `-E node_modules`          |
| `-p`  | — *Filtro*                 | SUF  | —                 | Solo incluye archivos que terminen en SUF.                        | `-p _test.py`              |
| `-k`  | — *Filtro*                 | EXT  | —                 | Añade una extensión extra (con punto).                            | `-k .md`                   |
| `-f`  | — *Miscelánea*             | FILE | `dump.txt`        | Archivo de salida.                                                | `-f auditoría.txt`         |
| `-n`  | — *Recorte*                | INT  | —                 | Longitud de cabeza (solo) o línea inicial (con `-N`).             | `-n 150`                   |
| `-N`  | — *Recorte*                | INT  | —                 | Línea final (inclusive), requiere `-n`.                           | `-n 10 -N 50`              |
| `-H`  | — *Recorte*                | FLAG | false             | Conserva la primera línea útil aunque quede fuera del rango.      | `-H`                       |
| `-t`  | — *Comportamiento*         | FLAG | false             | Muestra solo encabezados (sin cuerpo).                            | `-t`                       |
| `-c`  | — *Limpieza*               | FLAG | false             | Elimina comentarios simples.                                      | `-c`                       |
| `-C`  | — *Limpieza*               | FLAG | false             | Elimina **todos** los comentarios (anula `-c`).                   | `-C`                       |
| `-S`  | — *Limpieza*               | FLAG | false             | Conserva líneas en blanco.                                        | `-S`                       |
| `-i`  | — *Limpieza*               | FLAG | false             | Elimina sentencias `import`.                                      | `-i`                       |
| `-I`  | — *Limpieza*               | FLAG | false             | Elimina `export` / `module.exports`.                              | `-I`                       |
| —     | `--odoo`                   | FLAG | false             | Atajo: incluye `.py`, `.xml`, `.csv`, `.js`.                      | `--odoo`                   |
| —     | `--py`                     | FLAG | off               | Incluye archivos Python.                                          | `--py`                     |
| —     | `--no-py`                  | FLAG | off               | Excluye Python aunque esté incluido.                              | `--no-py`                  |
| …     | (igual para Dart/XML/CSV…) |      |                   |                                                                   |                            |
| —     | `--ia-prompt`              | FILE | —                 | Plantilla con `{dump_data}` para ChatGPT.                         | `--ia-prompt pregunta.tpl` |
| —     | `--ia-output`              | FILE | —                 | Archivo donde guardar la respuesta de ChatGPT.                    | `--ia-output respuesta.md` |
| —     | `--upgrade`                | FLAG | false             | Descarga la última versión y reemplaza la copia local.            | `--upgrade`                |
| `-l`  | `--lang`                   | CODE | `ES`              | Idioma UI: `ES` o `EN` (case‑insensitive).                        | `-l EN`                    |
| `-h`  | `--help`                   | FLAG | —                 | Muestra ayuda y sale.                                             | —                          |

---

## 6 · Modelo conceptual

1. **Raíces** – Puntos de partida (`‑a`) recorridos recursivamente.
2. **Conjunto de extensiones** – Construido a partir de flags de inclusión/exclusión y `‑k`.
3. **Filtros** – Patrones de ruta, directorios vetados, sufijos de nombre.
4. **Pipeline de limpieza** – Comentarios → imports/exports → líneas en blanco.
5. **Recorte** – Cabeza/cola opcional con preservación de cabecera.
6. **Montaje del dump** – Cada archivo se precede de `===== /ruta/abs =====`.
7. **Post‑procesado** – Envío opcional a ChatGPT.

---

## 7 · Profundizando en ficheros de directivas

### 7.1 Inline (`‑x`) – Paquetes de flags

Objetivo: compartir un set común de opciones entre ejecuciones.

**Puntos clave**

* Se parsea **antes** del CLI normal; el último flag gana.
* Soporta comentarios (`#` o `//` al final) y `‑a` con múltiples valores.

`defaults.dct`:

```text
--odoo            // preset multilenguaje
-c                # quita comentarios simples
-n 120            // solo primeras 120 líneas
-a addons         // raíz 1
-a tests          // raíz 2
```

Uso:

```bash
ghconcat -x defaults.dct -k .md -a docs
```

Aquí `.md` y `docs/` se añaden *después* de expandir `defaults.dct`.

---

### 7.2 Batch (`‑X`) – Trabajos independientes

Cada línea no comentada lanza **otro** trabajo de concatenación.
Reglas de herencia:

1. Padre → hijo, `OR` lógico para booleanos.
2. Listas (`-e`, `-E`, `-p`, `-k`) se concatenan.
3. El hijo puede negar booleanos heredados (`--no-*`).
4. Está **prohibido** anidar `‑X` dentro de un batch (evita recursión).

`ci.bat` (ejemplo realista):

```text
# Flags base
--odoo -c -i -H

# ─── Pruebas de backend ──────────────────────────────────────────────
-a addons
-p _test.py
--no-js --no-xml

# ─── Web assets: conservar comentarios para ESLint ───────────────────
-a web/static/src
--no-py --no-csv
-S
-I
```

Ejecución:

```bash
ghconcat -X ci.bat -f ci_bundle.txt
```

`ci_bundle.txt` contendrá ambos dumps, en orden.

---

## 8 · Recetas y flujos de trabajo

### 8.1 Diff “narrativo” para revisión

```bash
ghconcat --odoo -C -i -a addons/new_feature -f historia.txt
ghconcat --odoo -C -i -a addons/new_feature -p _old.py -f base.txt
diff -u base.txt historia.txt > review.patch
```

### 8.2 Compresión previa a LLM + resumen

```bash
ghconcat --py --dart --xml -C -i -I -S -a src \
         --ia-prompt ai/resumir.tpl \
         --ia-output ai/resumen.md \
         -l EN
```

`resumir.tpl`:

```text
Resume los siguientes cambios de código enfatizando el impacto arquitectónico:

{dump_data}
```

---

## 9 · Integración con ChatGPT

* **Seguridad de ida y vuelta** Si la llamada remota falla, tu dump local permanece intacto.
* **Diseño de prompt** Incluye `{dump_data}`; el resto es tuyo.
* **Cambio de idioma** `‑l ES` sustituye solo la palabra **English** por **Spanish** en el system prompt.
* **Timeout** 120 s fijos; exporta `DEBUG=1` para trazas completas.

---

## 10 · Proceso de actualización

Cron semanal automático:

```bash
0 4 * * 1  ghconcat --upgrade >> /var/log/ghconcat-upgrade.log 2>&1
```

Manual:

```bash
ghconcat --upgrade   # compara hashes antes de sobrescribir
```

---

## 11 · Variables de entorno y códigos de salida

| Variable         | Efecto                                     |
| ---------------- | ------------------------------------------ |
| `OPENAI_API_KEY` | Habilita funciones de ChatGPT.             |
| `DEBUG=1`        | Muestra tracebacks en errores inesperados. |

| Código | Significado                            |
| ------ | -------------------------------------- |
| 0      | Éxito                                  |
| 1      | Error fatal (flags incorrectos, IO, …) |
| 130    | Interrupción por teclado (`Ctrl‑C`)    |

---

## 12 · Solución de problemas

| Síntoma                               | Solución                                                                       |
| ------------------------------------- |--------------------------------------------------------------------------------|
| *“No active extension after filters”* | Revisa flags `--no-*` o añade `-k .ext`.                                       |
| Dump vacío                            | ¿Olvidaste pasar alguna raíz con `‑a`? ¿Filtro `-p` demasiado restrictivo?     |
| Petición a ChatGPT se cuelga          | Comprueba conexión, API key y que el dump ≤ 128 k tokens (≈ 350 k caracteres). |

---

## 13 · Preguntas frecuentes

<details>
<summary>¿Puedo anidar <code>-X</code> dentro de otro batch?</summary>
No. Se bloquea para evitar bucles infinitos. Lanza varios `‑X` de nivel superior si necesitas algo complejo.
</details>

<details>
<summary>¿Cómo incluyo código generado como <code>.g.dart</code>?</summary>
Se ignoran por defecto. Añade `-p .g.dart` o ajusta la expresión regular en `collect_files()`.
</details>

---

## 14 · Contribuir

* Estilo: **PEP 8**, `ruff`, `mypy --strict`.
* Tests: `pytest -q`.
* Commits: `<scope>: <asunto>` (sin punto final).
* Firma tus commits (`git config --global user.signingkey …`).

---

## 15 · Licencia

MIT. Consulta `LICENSE` para la redacción completa.

---

¡Con esta guía en español, cualquier desarrollador puede instalar, entender y sacar el máximo partido a **ghconcat**, desde tareas puntuales hasta integraciones avanzadas en CI/CD y flujos con IA!
