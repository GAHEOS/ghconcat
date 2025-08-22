# Academic Pipeline – Ejemplo “Quantum Computing & Photonics”

Bienvenido al directorio **examples/academic\_pipeline**.
Aquí encontrarás un flujo completo ‑basado en **ghconcat** e impulsado por IA‑ que ilustra cómo transformar un corpus
heterogéneo (papers, notas de laboratorio, resúmenes de conferencias…) en un informe académico pulido mediante la
colaboración de varias “personas” artificiales.

> **Objetivo**: demostrar, de forma práctica, cómo orquestar múltiples etapas de lectura, síntesis, revisión y edición
> usando únicamente un archivo de directivas (`academic_pipeline.gctx`) y una colección de *prompts* Markdown.

---

## 1 · ¿Qué hace el pipeline?

1. **Recolecta la materia prima**
   *Descarga* dos artículos abiertos de arXiv y *limpia* tus notas Markdown locales.
   Resultado → `workspace/sources.md` y `workspace/notes.md`.

2. **Borrador junior**
   Un “investigador junior” (modelo **o3**) lee el corpus y produce un primer esquema de la literatura.
   Resultado → `workspace/junior.out.md`.

3. **Revisión senior**
   Un “investigador sénior” (modelo **gpt‑4o**) refina, complementa y comenta el borrador.
   Resultado → `workspace/senior.out.md`.

4. **Crítica académica #1**
   Un “revisor ciego” emite observaciones críticas y calificaciones seccionadas.
   Resultado → `workspace/critic1.out.md`.

5. **Pulido de estilo**
   Un “editor científico” reescribe el texto para claridad y tono formal, aplicando las sugerencias.
   Resultado → `workspace/redraft.out.md`.

6. **Crítica académica #2**
   El revisor vuelve a evaluar la versión pulida y valida las mejoras.
   Resultado → `workspace/critic2.out.md`.

7. **Bundle final**
   ghconcat concatena el informe definitivo con encabezados de ruta absoluta para trazabilidad.
   Resultado → `workspace/final_report.md`.

Todo ello se ejecuta con **un solo comando** y deja rastros intermedios perfectamente auditables en `workspace/`.

---

## 2 · Cómo ejecutarlo

```bash
# Requisitos previos
export OPENAI_API_KEY="tu_token_aqui"

# Lanzar la pipeline
ghconcat -x academic_pipeline.gctx -O
```

Al finalizar:

* **STDOUT** mostrará el informe final.
* **workspace/** contendrá cada artefacto intermedio, ideal para inspección o reutilización.
* No se altera ningún archivo de tus notas originales: ghconcat es read‑only.

---

## 3 · Estructura de carpetas esperada

```
examples/
└─ academic_pipeline/
   ├─ academic_pipeline.gctx   # Directivas ghconcat
   ├─ prompts/                 # Prompts Markdown para cada rol IA
   │  ├─ junior.md
   │  ├─ senior.md
   │  ├─ critic.md
   │  └─ editor.md
   ├─ notes/                   # Tus apuntes locales (Markdown)
   │  └─ ...md
   └─ workspace/               # Se crea en tiempo de ejecución
```

> **Tip**: reemplaza, añade o elimina notas/artículos y ajusta la variable global `topic` al vuelo; el pipeline se
> adapta sin más cambios.

---

## 4 · Por qué es interesante

* **Orquestación declarativa**: todas las etapas, parámetros y variables viven en un único archivo legible.
* **Trazabilidad absoluta**: cada transformación se guarda; puedes “rebobinar” cualquier fase.
* **Colaboración ficticia**: diferentes *personas IA* aportan perspectivas complementarias (junior, senior, revisor,
  editor).
* **Facilidad de réplica**: cambia los prompts, los modelos o la profundidad de scraping — el esqueleto permanece igual.

---

## 5 · Siguiente paso

Prueba a:

* **Cambiar el tema** (`-E topic="..."`) y añadir nuevas seeds `-F <url>` para ver cómo varía la síntesis.
* **Intercambiar modelos** (`--ai-model o3 | gpt-4o | …`) y comparar estilos de salida.
* **Insertar tu propio prompt** para, por ejemplo, generar tablas de datos o resúmenes ejecutivos.

¡Explora, modifícalo y descubre cómo **ghconcat** puede transformar tu flujo de investigación!
