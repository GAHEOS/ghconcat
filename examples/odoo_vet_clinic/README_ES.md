# Ejemplo de *pipeline* «gaheos \_vet\_clinic» (README \_es)

Este subdirectorio muestra, paso a paso, cómo **ghconcat** y la IA pueden generar un *addon* completo de Odoo 17
‑incluyendo pruebas unitarias‑ a partir de una simple especificación funcional.
Todo el flujo se describe en **`dev_pipeline.gctx`** y se apoya en una colección de *prompts* Markdown.

---

## 1 · Propósito

*Crear un módulo veterinario mínimo pero listo para producción* (`gaheos_vet_clinic`) sin escribir una sola línea de
código manualmente.
El *pipeline* orquesta a seis “roles” artificiales (Senior Dev → QA → Senior Dev v2 → Tester → QA Tests → Tester v2)
para:

1. Generar el código inicial del addon.
2. Revisarlo, corregirlo y endurecerlo.
3. Redactar y pulir pruebas unitarias.
4. Entregar un **bundle final** (addon + tests) reproducible.

---

## 2 · Flujo resumido

| Paso | Contexto (`[ ]`) | Rol IA           | Acción principal                                     | Artefacto                           |
|------|------------------|------------------|------------------------------------------------------|-------------------------------------|
| 0    | `[spec]`         | —                | Convierte la especificación Markdown en texto limpio | `workspace/spec.txt`                |
| 1    | `[senior_code]`  | Senior Developer | Genera el addon completo                             | `workspace/senior_module.md`        |
| 2    | `[qa_feedback]`  | QA               | Audita el código y emite tabla de hallazgos          | `workspace/qa_feedback.md`          |
| 3    | `[addon_code]`   | Senior Developer | Refactoriza corrigiendo issues High/Med              | `workspace/revised_module.md`       |
| 4    | `[tests_v1]`     | Tester           | Crea pruebas unitarias iniciales                     | `workspace/tests_v1.md`             |
| 5    | `[qa_tests]`     | QA               | Revisa cobertura y calidad de tests                  | `workspace/qa_tests_feedback.md`    |
| 6    | `[tests_v2]`     | Tester           | Mejora tests según feedback                          | `workspace/tests_v2.md`             |
| 7    | `[final]`        | —                | Concatena addon + tests para humanos                 | `final/gaheos_vet_clinic_bundle.md` |

Cada archivo intermedio se conserva para trazabilidad y posibles inspecciones.

---

## 3 · Requisitos previos

* **Python ≥ 3.8**
* **ghconcat** instalado:

  ```bash
  pip install ghconcat
  ```
* Variable de entorno **`OPENAI_API_KEY`** con tu token.

---

## 4 · Ejecución

Desde la raíz del ejemplo:

```bash
export OPENAI_API_KEY="tu_token_aquí"
ghconcat -x dev_pipeline.gctx -O
```

Al terminar:

* El informe final aparece en **STDOUT** y se guarda en `final/gaheos_vet_clinic_bundle.md`.
* Todos los pasos intermedios viven en `workspace/` para que puedas auditar, re‑correr o modificar cualquier fase.

---

## 5 · Estructura de carpetas

```
examples/
└─ gaheos_vet_clinic/
   ├─ dev_pipeline.gctx   # Descripción declarativa del flujo
   ├─ docs/
   │  └─ spec_vet_clinic.md
   ├─ prompts/            # Prompts de cada rol
   │  ├─ senior.md
   │  ├─ senior_revision.md
   │  ├─ qa.md
   │  ├─ tester.md
   │  ├─ qa_tests.md
   │  └─ tester_improve.md
   └─ workspace/          # Generado automáticamente (artefactos)
```

---

## 6 · Personalización rápida

* **Añade / edita la especificación** en `docs/spec_vet_clinic.md` para cambiar el alcance del addon.
* **Cambia los modelos IA** (`--ai-model`) en cada contexto para comparar estilos o costos.
* **Inserta tus prompts** (por ejemplo, para generar documentación automática) y referencia su ruta en
  `dev_pipeline.gctx`.

---

## 7 · Por qué usar este ejemplo

* **Demuestra productividad**: un módulo funcional + tests listos para CI sin intervención humana.
* **Muestra buenas prácticas de ghconcat**: variables globales (`-E`), wrapping, encabezados y artefactos trazables.
* **Sirve como plantilla**: clónalo, cambia la especificación y tendrás un nuevo addon en minutos.

¡Explora, adapta y lleva tu desarrollo Odoo al siguiente nivel con **ghconcat**!
