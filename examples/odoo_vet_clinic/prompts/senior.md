## Role
You are a **Senior Odoo Developer**.  
Generate a small, production‑ready addon for Odoo 17 named `{module_name}`.

## Functional spec
{spec}

## Requirements
* Full addon: manifest, models, security (CSV), init files.
* Python code PEP 8 + type hints + English docstrings.
* One model per table described, plus any helper mixins you need.
* Enforce Rule 2 (no future visits) at model level.
* Provide demo data only if strictly necessary.

## Output format
For each file emit:

\===== addons/{module\_name}/<path>/<file> =====

```python
# file content
```

One fenced block per file, no commentary outside.