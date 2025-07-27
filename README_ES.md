# ghconcat

> **Concatenador de archivos multilenguaje con presets para Odoo y Flutter, recorte avanzado, orquestación por lotes y descarga en ChatGPT, todo en un único script Python auto‑contenidos.**

`ghconcat` recorre tu árbol de proyecto, selecciona los archivos que realmente importan, **elimina el ruido**, opcionalmente corta por rango de líneas y concatena el resultado en un volcado determinista y legible por humanos.  
Utiliza el volcado para diffs en revisiones de código, como contexto para un LLM, o como “fuente de verdad de archivo único” en auditorías automatizadas.

---

## 0 · TL;DR

```bash
# 1 – Resumen de 100 líneas de cada archivo Python & XML dentro de addons/ + web/, listo para ChatGPT:
ghconcat -g py -g xml -C -i -n 100 \
         -a addons -a web \
         -K SUMMARY=1.0 -t ai/prompt.tpl -Q -o ai/reply.md   # -K (var ent.), -o opcional pero recomendado

# 2 – Mismo volcado, pero **solo listar las rutas de archivo** (sin cuerpo)
ghconcat -g py -g xml -a addons -l

# 3 – Crear un “bundle de CI” fusionando tres trabajos independientes
ghconcat \
  -X conf/ci_backend.bat \
  -X conf/ci_frontend.bat \
  -X conf/ci_assets.bat \
  -o build/ci_bundle.txt
````

---

## Tabla de Contenidos

1. [Filosofía](#1--filosofía)
2. [Matriz de Funcionalidades](#2--matriz-de-funcionalidades)
3. [Instalación](#3--instalación)
4. [Inicio Rápido](#4--inicio-rápido)
5. [Referencia Completa de CLI](#5--referencia-completa-de-cli)
6. [Modelo Conceptual](#6--modelo-conceptual)
7. [Archivos de Directivas `-x` y `-X`](#7--archivos-de-directivas-x-y-x)
   1. [Paquetes Inline `-x`](#71-x--paquetes-inline)
   2. [Trabajos por Lotes `-X`](#72-x--trabajos-por-lotes)
8. [Recetas](#8--recetas)
9. [Pasarela ChatGPT](#9--pasarela-chatgpt)
10. [Auto‑Actualización](#10--autoactualización)
11. [Entorno y Códigos de Salida](#11--entorno-y-códigos-de-salida)
12. [Solución de Problemas](#12--solución-de-problemas)
13. [FAQ](#13--faq)
14. [Contribuir](#14--contribuir)
15. [Licencia](#15--licencia)

---

## 1 · Filosofía

| Principio                       | Razonamiento                                                             |
| ------------------------------- | ------------------------------------------------------------------------ |
| **Contexto de un solo comando** | No hay que abrir quince archivos en tu editor solo para “entender” un PR |
| **Volcado determinista**        | Mismo input ⇒ mismo output → perfecto para diffs en CI                   |
| **Orquestación componible**     | Paquetes inline (`‑x`), trabajos por lotes (`‑X`), herencia de flags     |
| **Seguridad de solo lectura**   | Nunca reescribe tus fuentes; todo ocurre en memoria                      |
| **Flujo AI‑first**              | Integración nativa (`‑Q`) con un prompt de sistema de nivel producción   |

---

## 2 · Matriz de Funcionalidades

| Dominio                   | Destacados                                                                                                  |
| ------------------------- |-------------------------------------------------------------------------------------------------------------|
| **Descubrimiento**        | Recorrido recursivo, exclusión de rutas y directorios, filtro por sufijo, **omisión de archivos ocultos**   |
| **Conjunto de lenguajes** | Mezcla de inclusiones (`‑g py`,`‑g xml`) y exclusiones (`‑G js`). Presets: `odoo`, `flutter`                |
| **Limpieza**              | Elimina comentarios (`‑c` ➜ simples, `‑C` ➜ todos), imports (`‑i`), exports (`‑I`), líneas en blanco (`‑s`) |
| **Recorte**               | Mantener *n* líneas (`‑n`), rangos arbitrarios (`‑n` + `‑N`), preservación de cabecera (`‑H`)               |
| **Lotes**                 | Paquetes (`‑x`) y trabajos jerárquicos (`‑X`) con reglas de herencia                                        |
| **Plantillas**            | Placeholder `{dump_data}`, alias personalizados (`‑k ALIAS`) y variables de entorno (`‑K VAR=VAL`)          |
| **Puente LLM**            | Timeout robusto de 1800 s, wrapping seguro JSON, bloques de código automáticos (`‑u`)                       |
| **Salida**                | Archivo `‑o` opcional; sin él el volcado solo se devuelve (modo librería)                                   |
| **Rutas de cabecera**     | **Relativas por defecto**; añade `‑p/‑‑absolute‑path` para rutas absolutas                                  |
| **Auto‑actualización**    | `--upgrade` obtiene el último commit de GitHub en una copia atómica                                         |

---

## 3 · Instalación

> ghconcat es Python puro ≥ 3.8 y **no tiene dependencias de ejecución externas**
> (las funciones ChatGPT son opcionales; véase más abajo).

### Unix‑like (Linux / macOS)

```bash
# 1. Clonar el repositorio
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat

# 2. Instalar el paquete (sistema o venv)
python3 setup.py install  # usa setuptools

# 3. Copiar el lanzador a un bin personal
mkdir -p ~/.bin
cp ghconcat.py ~/.bin/ghconcat
chmod +x ~/.bin/ghconcat

# 4. Añadir ~/.bin al PATH (si no está)
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc
source ~/.bashrc   # recarga, o reinicia la shell

# 5. Prueba rápida
ghconcat -h
```

### Windows (PowerShell)

```powershell
# 1. Clonar e instalar
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python setup.py install

# 2. Copiar el script a un directorio bin de usuario
$Bin="$env:USERPROFILE\bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Copy-Item ghconcat.py "$Bin\ghconcat.py"

# 3. Añadir ese directorio al PATH (persistente)
[Environment]::SetEnvironmentVariable('Path', "$Bin;$env:Path", 'User')

# 4. Alias para comodidad (sesión actual)
Set-Alias ghconcat python "$Bin\ghconcat.py"

# 5. Verificar
ghconcat -h
```

### Opcional: integración con ChatGPT

```bash
pip install openai
export OPENAI_API_KEY=sk-********************************
# o, en Windows PowerShell:
# [Environment]::SetEnvironmentVariable('OPENAI_API_KEY','sk-********************************','User')
```

> **Consejo:** Para mantener ghconcat global mientras trabajas en entornos virtuales, deja `~/.bin` antes del venv en tu `PATH`, o crea un symlink del lanzador dentro de `bin/` de cada entorno.

---

## 4 · Inicio Rápido

| Tarea                                                                               | Comando                                                                          |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Volcar todos los archivos **Python** en `src/` a `dump.txt`                         | `ghconcat -g py -a src -o dump.txt`                                              |
| Auditar un **addon Odoo**, eliminar **todos** los comentarios e imports, 100 líneas | `ghconcat -g odoo -C -i -n 100 -a addons/sale_extended`                          |
| Simulación (*solo listar*)                                                          | `ghconcat -g odoo -a addons/sale_extended -l`                                    |
| Enviar volcado comprimido a ChatGPT con `tpl/prompt.md`, guardar respuesta          | `ghconcat -g py -g dart -C -i -a src -t tpl/prompt.md -Q -o reply.md`            |
| Fusionar tres archivos de lote independientes                                       | `ghconcat -X ci_backend.bat -X ci_frontend.bat -X ci_assets.bat -o build/ci.txt` |

---

## 5 · Referencia Completa de CLI

*(los flags se agrupan por temática; los repetibles se marcan explícitamente)*

| Flags                          | Propósito / Notas                                                                 |
| ------------------------------ |-----------------------------------------------------------------------------------|
| **Orquestación de lotes**      |                                                                                   |
| `‑x FILE`                      | *Paquete inline* – expande flags desde FILE **antes** del parseo                  |
| `‑X FILE` *(repetible)*        | *Trabajo por lote* – ejecuta FILE como trabajo independiente y fusiona su volcado |
| **Descubrimiento de archivos** |                                                                                   |
| `‑a PATH` *(repetible)*        | Añade raíz PATH (archivo o directorio)                                            |
| `‑r DIR`                       | Raíz lógica para resolver rutas relativas                                         |
| `‑w DIR`                       | Workspace (base de destino de salida; por defecto=`cwd`)                          |
| `‑e DIR` *(repetible)*         | Excluye recursivamente el directorio DIR                                          |
| `‑E PAT` *(repetible)*         | Excluye cualquier ruta que contenga PAT                                           |
| `‑S SUF` *(repetible)*         | Solo incluye archivos que terminen con SUF                                        |
| **Conjunto de lenguajes**      |                                                                                   |
| `‑g LANG` *(repetible)*        | Incluye lenguaje/extensión (`py`, `xml`, `.csv`, preset `odoo`)                   |
| `‑G LANG` *(repetible)*        | Excluye lenguaje/extensión                                                        |
| **Recorte**                    |                                                                                   |
| `‑n NUM`                       | Mantiene NUM líneas desde `first_line` (`‑N`) o desde arriba                      |
| `‑N LINE`                      | Línea base 1 donde inicia el recorte                                              |
| `‑H`                           | Duplica la línea 1 original si quedó fuera del recorte                            |
| **Limpieza**                   |                                                                                   |
| `‑c` / `‑C`                    | Quita comentarios simples / todos                                                 |
| `‑i` / `‑I`                    | Elimina `import` / `export`                                                       |
| `‑s`                           | Mantiene líneas en blanco (sin él, se descartan)                                  |
| **Salida & plantillas**        |                                                                                   |
| `‑o FILE`                      | Archivo de salida (opcional; sin él, volcado solo vía API)                        |
| `‑u LANG`                      | Envuelve cada bloque en fences Markdown «`LANG`»                                  |
| `‑t FILE`                      | Plantilla con placeholders `{dump_data}`                                          |
| `‑k ALIAS`                     | Expone este volcado como `{ALIAS}` al template **padre** (máx 1 por nivel)        |
| `‑K VAR=VAL` *(repetible)*     | Variables clave‑valor extra para interpolación                                    |
| `‑l`                           | Solo lista archivos (sin cuerpo)                                                  |
| `‑p` / `‑‑absolute‑path`       | Muestra rutas absolutas en cabeceras (por defecto relativas a `--root`)           |
| **Pasarela AI**                |                                                                                   |
| `‑Q`                           | Envía volcado renderizado a ChatGPT                                               |
| `‑m MODEL`                     | Modelo OpenAI (por defecto `o3`)                                                  |
| `‑M FILE`                      | Prompt de sistema personalizado                                                   |
| **Miscelánea**                 |                                                                                   |
| `‑U`                           | Auto‑actualización desde GitHub                                                   |
| `‑L` ES \| EN                  | Idioma de CLI / prompt (ES por defecto)                                           |
| `‑h`                           | Ayuda                                                                             |

---

## 6 · Modelo Conceptual

```
┌──────────────┐    ┌─────────────┐    ┌─────────────────┐
│ 1· Raíces    │ →  │ 2· Filtros  │ →  │ 3· Lenguajes    │
└──────────────┘    └─────────────┘    └─────────────────┘
        ↓                      ↓                    ↓
 (recorrido FS)       (chequeo sufijo/ruta)   (incluir / excluir)
        └─────────────┬───────────────┬─────────────────┘
                      ↓
          4· Pipeline de limpieza → 5· Recorte → 6· Volcado
                      ↓
            7· Plantilla / ChatGPT
```

---

## 7 · Archivos de Directivas `‑x` y `‑X`

### 7.1 `‑x` – Paquetes Inline

*Cargados **antes** de `argparse`*, por lo que pueden añadir **nuevos** flags y sobreescribir entrada del usuario.

```text
# defaults.dct
-g odoo        # preset
-c -i          # limpieza
-n 120         # recorte
-a addons -a tests
```

```bash
ghconcat -x defaults.dct -G js -a docs -o dump.txt
```

### 7.2 `‑X` – Trabajos por Lotes

Cada **línea no vacía** se analiza con la semántica completa de CLI:

```text
# ci_backend.bat
-g py -a addons -e .git
-g py -g xml -a migrations -C -i
```

Herencia de flags:

| Tipo        | Comportamiento             |
| ----------- | -------------------------- |
| Booleanos   | OR‑merge                   |
| Listas      | Concatenados               |
| Singletones | El hijo sobrescribe        |
| Prohibidos  | `‑x`, `‑t`, `‑o`, flags AI |

---

## 8 · Recetas

> Todos los comandos asumen una shell Unix‑like; adapta rutas/comillas en Windows.

<details>
<summary><strong>8.1 Story‑diff para revisión de código (cabeceras relativas)</strong></summary>

Muestra el contexto histórico completo de un pull‑request comparando dos volcados
con las **cabeceras relativas por defecto**:

```bash
# baseline (main)
ghconcat -g odoo -C -i -a addons/sale -o /tmp/base.txt

# Rama PR (checkout)
ghconcat -g odoo -C -i -a addons/sale -o /tmp/head.txt

# diff legible
diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>8.2 Auditoría con rutas absolutas (CI server‑side)</strong></summary>

Algunas tuberías CI necesitan rutas **absolutas** para enlaces en informes HTML:

````bash
ghconcat -g py -g xml -C -i \
         -a src -a migrations \
         -p \                    # cabeceras absolutas
         -u py \                 # fences ```py```
         -o build/audit.txt
````

El archivo resultante puede convertirse en HTML con un conversor Markdown trivial.

</details>

<details>
<summary><strong>8.3 Resumen arquitectónico automático (ChatGPT, EN)</strong></summary>

```bash
ghconcat -g py -g dart -C -i -s -a src \
         -t ai/summarise.tpl \              # plantilla con {dump_data}
         -K version=$(git rev-parse --short HEAD) \
         -Q -o ai/summary.md -L EN
```

* `-Q` envía la plantilla renderizada a ChatGPT y guarda la respuesta en `ai/summary.md`.
* `-K` inserta el hash del commit para referencia en la respuesta.

</details>

<details>
<summary><strong>8.4 Bundle de CI con tres trabajos independientes</strong></summary>

Agrupa backend, frontend y assets en un artefacto determinista:

```bash
ghconcat -X conf/ci_backend.bat  \
         -X conf/ci_frontend.bat \
         -X conf/ci_assets.bat   \
         -o build/ci_bundle.txt
```

Cada `.bat` se analiza línea por línea con semántica CLI completa; los flags
siguen las reglas de herencia descritas en §7.2.

</details>

<details>
<summary><strong>8.5 Hook pre‑commit: Lint + concatenar solo archivos cambiados</strong></summary>

```bash
# .git/hooks/pre-commit (chmod +x)
changed=$(git diff --cached --name-only --relative | tr '\n' ' ')
[ -z "$changed" ] && exit 0

# ejecutar ruff / mypy…
ruff $changed && mypy --strict $changed || exit 1

# concatenar lo staged para revisión final
ghconcat -g py -C -i -a $changed -o /tmp/pre_commit_dump.txt
less /tmp/pre_commit_dump.txt   # vistazo opcional
```

El hook aborta el commit si el lint falla; de lo contrario ofrece un volcado
unificado de las líneas staged, ayudándote a detectar prints de debug antes de push.

</details>

<details>
<summary><strong>8.6 One‑liner: generar “fuente‑de‑verdad” Markdown para docs</strong></summary>

````bash
ghconcat -g dart -g js -C -i \
         -a lib -a web \
         -u js           \   # fences ```js```
         -o docs/src_of_truth.md
````

Los desarrolladores pueden enlazar a secciones estables por línea en tu base de conocimiento en lugar de archivos crudos.

</details>

---

## 9 · Pasarela ChatGPT

| Aspecto          | Detalle                                                                             |
| ---------------- |-------------------------------------------------------------------------------------|
| Prompt sistema   | Opinativo, bilingüe; sobrescribe con `‑M my_prompt.txt`                             |
| Placeholders     | Sustituye siempre `{dump_data}` más cualquier `‑K VAR=VAL` o `‑k alias`             |
| Seguridad tokens | Máx ≈ 128 k tokens (≈ 350 k chars) – aborta temprano con mensaje claro si se excede |
| Timeout          | 1800 s de pared                                                                     |
| Modos fallo      | Errores de red / cuota / formato ⇒ **exit ≠ 0**, volcado local intacto              |

---

## 10 · Auto‑Actualización

```bash
ghconcat --upgrade   # atómico; copia a ~/.bin/ghconcat (ajusta en código si quieres)
```

Añade al crontab:

```
0 6 * * MON  ghconcat --upgrade >/var/log/ghconcat-upgrade.log 2>&1
```

---

## 11 · Entorno y Códigos de Salida

| Variable / Valor | Significado                                      |
| ---------------- | ------------------------------------------------ |
| `OPENAI_API_KEY` | Habilita todas las funciones `‑Q`                |
| `DEBUG=1`        | Muestra tracebacks Python en errores inesperados |

| Código | Significado                        |
| ------ | ---------------------------------- |
| 0      | Éxito                              |
| 1      | Error fatal (flag inválido, IO, …) |
| 130    | Cancelado por usuario (`Ctrl‑C`)   |

---

## 12 · Solución de Problemas

| Síntoma                                                       | Solución                                                     |
| ------------------------------------------------------------- |--------------------------------------------------------------|
| *“After applying --exclude‑lang no active extension remains”* | Revisa tus `‑g/‑G`; filtraste **todo**                       |
| Volcado vacío / archivos faltantes                            | Comprueba raíces (`‑a`), sufijos (`‑S`), directorios ocultos |
| ChatGPT se cuelga                                             | Internet, API key, volcado <128 k tokens?                    |
| “Forbidden flag inside ‑X context”                            | Quita `‑o`, `‑t`, flags AI de esa línea de lote              |

---

## 13 · FAQ

<details>
<summary>¿Puedo anidar <code>-X</code> dentro de otro trabajo <code>-X</code>?</summary>
No; ghconcat lo bloquea para evitar recursión accidental.  
Ejecuta múltiples flags `‑X` a nivel superior.
</details>

<details>
<summary>¿Por qué se excluyen los archivos <code>*.g.dart</code>?</summary>
Suelen ser generados; ghconcat los ignora salvo que fuerces inclusión
con `‑S .g.dart` o modifiques el helper en <code>_collect_files()</code>.
</details>

<details>
<summary>¿Funciona la herramienta en Windows?</summary>
Sí – es Python puro 3.8+. Usa alias de PowerShell como se muestra en la instalación.
</details>

---

## 14 · Contribuir

* Estilo de código: **PEP8**, `ruff`, `mypy --strict`
* Tests: `pytest -q`
* Commits: `<scope>: <subject>` (sin punto final)
* Firmado: `git config --global user.signingkey …`

¡Se aceptan PRs!

---

## 15 · Licencia

MIT – ver `LICENSE` para el texto completo.
