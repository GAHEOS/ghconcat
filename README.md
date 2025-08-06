# ghconcat

> **Hierarchical, language‑agnostic file concatenator · ultra‑deterministic · zero external deps**

`ghconcat` walks your project tree, selects only the files you care about, **strips the noise** (comments, imports,
blank
lines, etc.), applies optional line‑range slicing and concatenates the result into a single, reproducible dump.  
Typical use‑cases:

* Giant but clean prompts for LLMs.
* Traceable artefacts in CI/CD.
* Code‑review bundles that stay line‑number‑stable.
* A *source of truth* you can embed in docs or knowledge bases.

---

## 0 · TL;DR – Quick Cheat‑Sheet

```bash
# 1 ─ Create a 120‑line dump per file for .py + .xml under addons/ and web/,
#     wrap each chunk in Markdown fences, pipe through OpenAI and save the
#     reply in ai/reply.md:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -u markdown \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Same discovery rules, but "dry‑run": list absolute paths only
ghconcat -s .py -s .xml -a addons -l -R

# 3 ─ Fully declarative multi‑step pipeline with contexts
ghconcat -x conf/pipeline.gctx -o build/artifact.txt
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

| Principle                | Rationale                                                                            |
|--------------------------|--------------------------------------------------------------------------------------|
| **Determinism first**    | Same input ⇒ identical dump – perfect for CI drift detection.                        |
| **Composable by design** | Mix one‑liners, directive files (`‑x`) and hierarchical contexts in a single script. |
| **Read‑only & atomic**   | Your sources are never touched; output is written only where you ask (`‑o`).         |
| **LLM‑ready**            | A single flag (`--ai`) bridges the dump to OpenAI.                                   |
| **Zero dependencies**    | Pure Python ≥3.8. The OpenAI bridge is optional (`pip install openai`).              |

---

## 2 · What’s New in v2

| Area                 | v1 behaviour                         | **v2 (current)**                                                       |
|----------------------|--------------------------------------|------------------------------------------------------------------------|
| **Batching**         | `‑X` (inherited) vs `‑x` (inline)    | **Only `‑x`**; each file is an isolated sandbox, contexts via `[ctx]`. |
| **Discovery flags**  | `‑g` / `‑G` by language              | **Removed** – use `‑s` / `‑S` by suffix                                |
| **Whitespace**       | `‑B` kept `\n`; no explicit opposite | `‑b` **strip** and `‑B` **keep** (tri‑state per context)               |
| **First‑line rules** | `‑M` (keep header when slicing)      | `‑m` **keep**, `‑M` **drop**                                           |
| **Header banner**    | Always on, disabled with `‑P`        | Off by default. Enable with `‑h`; suppress again with `‑H`.            |
| **Path style**       | `‑p` absolute / `‑P` no headers      | `‑R` absolute / `‑r` relative (default)                                |
| **Wrap fences**      | `‑u` enabled, no way to cancel       | `‑u LANG` enables · `‑U` cancels                                       |
| **List mode**        | `‑l` (list)                          | `‑l` list · `‑L` cancels inherited `‑l`                                |
| **Env vars**         | `‑e/-E` always propagated            | Now **only `‑E`** is inherited; `‑e` stays local                       |
| **Self‑upgrade**     | N/A                                  | `--upgrade` pulls the latest tag into `~/.bin/ghconcat`                |

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
<summary><strong>Optional – enable the OpenAI bridge</strong></summary>

```bash
python3 -m pip install openai
export OPENAI_API_KEY=sk-********************************
```

</details>

---

## 4 · Quick Start

| Goal / Task                                         | Command                                                                                  |
|-----------------------------------------------------|------------------------------------------------------------------------------------------|
| Concatenate every **.py** under `src/` → `dump.txt` | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Audit an **Odoo add‑on** with no comments/imports   | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Dry‑run (relative listing)                          | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Dump `.py + .dart`, wrap and send to ChatGPT        | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Produce a multi‑step artefact via contexts          | `ghconcat -x ci_pipeline.gctx -o build/ci_bundle.txt`                                    |

---

## 5 · CLI Reference

*Repeatable flags are marked **·***

| Category                | Flag(s) & Argument(s)                        | Description                                       |
|-------------------------|----------------------------------------------|---------------------------------------------------|
| **Discovery**           | `‑w DIR` / `‑W DIR`                          | Content root / workspace for templates & outputs  |
|                         | `‑a PATH`· / `‑A PATH`·                      | Include / exclude file or directory               |
|                         | `‑s SUF`· / `‑S SUF`·                        | Include / exclude by suffix (`.py`, `.yml`, …)    |
| **Line Slicing**        | `‑n NUM`, `‑N LINE`                          | Max lines / start line (1‑based)                  |
|                         | `‑m` / `‑M`                                  | Keep / drop original line1 if sliced              |
| **Clean‑up**            | `‑c` / `‑C`                                  | Strip simple / all comments                       |
|                         | `‑i` / `‑I`                                  | Remove imports / exports                          |
|                         | `‑b` / `‑B`                                  | Strip / keep blank lines                          |
| **Templating & Output** | `‑t FILE` / `‑t none`                        | Jinja‑lite template; `none` cancels inheritance   |
|                         | `‑o FILE`                                    | Write result to file                              |
|                         | `‑u LANG` / `‑U`                             | Wrap fenced `LANG` blocks / cancel inherited wrap |
|                         | `‑h` / `‑H`                                  | Show / hide heavy headers                         |
|                         | `‑r` / `‑R`                                  | Relative / absolute paths in headers              |
|                         | `‑l` / `‑L`                                  | List mode / cancel inherited list                 |
|                         | `‑e VAR=VAL`· / `‑E VAR=VAL`·                | Local / global variable                           |
| **AI Bridge**           | `--ai`                                       | Enable OpenAI call                                |
|                         | `--ai-model`, `--ai-temperature`, …          | Model parameters                                  |
|                         | `--ai-system-prompt FILE`, `--ai-seeds FILE` | System prompt & JSONL seeds                       |
| **Batching**            | `‑x FILE`·                                   | Execute directive file (with contexts)            |
| **Misc**                | `--upgrade`                                  | Self‑upgrade ghconcat                             |

*Any value‑flag can be neutralised by passing `none` in a child context.*

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

`‑e/-E` variables and context aliases may be interpolated **at any later stage**.

---

## 7 · Directive Files & Contexts

### 7.1 The `‑x` file

* Each `‑x` opens an **isolated environment**; its flags do not leak to the next `‑x`.
* Inside the file, every line is parsed like CLI; contexts are created with `[name]`.

```gctx
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

**Inheritance rules**

| Attribute type | Merge rule                            |
|----------------|---------------------------------------|
| Lists          | concatenate (`suffix`, `add_path`, …) |
| Booleans       | Logical OR (once enabled it stays on) |
| Scalars        | Child overrides (`‑w`, `‑t`, …)       |
| Non‑inherited  | `‑o`, `--ai`, `‑U`, `‑L`              |

Local variables (`‑e`) **do not** propagate; global variables (`‑E`) do.

---

## 8 · Templating & Variables

* Any placeholder `{var}` is replaced with:

    * Context aliases (`[ctx]` exposes `{ctx}`, `{_r_ctx}`, `{_t_ctx}`, `{_ia_ctx}`)
    * `ghconcat_dump` (the global concatenation across contexts)
    * Variables from `‑e` (local) and `‑E` (global)

* `$VAR` expansion happens inside flags before parsing.

---

## 9 · AI Gateway

| Aspect          | Detail                                                              |
|-----------------|---------------------------------------------------------------------|
| Activation      | `--ai` + `OPENAI_API_KEY` in the environment                        |
| Models          | Any supported by OpenAI (default **o3**)                            |
| Seeds JSONL     | Inherited unless `--ai-seeds none`                                  |
| System prompt   | Template‑aware (`--ai-system-prompt`)                               |
| Timeout         | 1800s wall‑clock                                                    |
| Output handling | Reply is written to `‑o` (or a temp file) and assigned to `_ia_ctx` |

> ⚠️ The entire rendered prompt is sent to the LLM provider.

---

## 10 · Workspaces & Outputs

* `‑w` defines the content root to scan.
* `‑W` is the workspace relative to `‑w` (templates, prompts, outputs).
* Relative paths inside a context are resolved against the current `‑w` / `‑W`.

---

## 11 · Recipes

<details>
<summary><strong>11.1 Diff‑friendly dump for code‑review</strong></summary>

```bash
# main branch
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# feature branch (after checkout)
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>11.2 Produce a “source‑of‑truth” Markdown</strong></summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary><strong>11.3 Context pipeline with AI post‑processing</strong></summary>

```gctx
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
ghconcat -x pipeline.gctx
```

</details>

---

## 12 · Migrating from v1

| v1 Flag / Concept | Replacement in v2         |
|-------------------|---------------------------|
| `‑g / ‑G`         | `‑s / ‑S` + plain suffix  |
| `‑X`              | `‑x` + contexts `[ctx]`   |
| `‑M` (first line) | `‑m` (keep) / `‑M` (drop) |
| `‑P`              | `‑H` (suppress headers)   |
| `‑p`              | `‑R` (absolute) / `‑r`    |
| `‑u none`         | `‑U`                      |

Quick example:

```bash
# v1 style
ghconcat -g py -C -i -n 80 -a src -X bundle.gcx

# v2 style
ghconcat -s .py -C -i -n 80 -a src -x bundle.gcx
```

---

## 13 · Troubleshooting

| Symptom                         | Hint                                                          |
|---------------------------------|---------------------------------------------------------------|
| Empty dump                      | Check `‑a` / `‑s`; verify exclusions `‑A/‑S`.                 |
| ChatGPT timeout                 | Network? quota? Prompt >128k tokens?                          |
| Unresolved template var `{foo}` | Define with `‑e foo=bar` or expose a context alias.           |
| Duplicate headers               | Avoid mixing `‑h` inside contexts with a root‑level template. |
| `flag expects VAR=VAL`          | Fix the syntax in `‑e` or `‑E`.                               |
| Imports/exports still present   | Use `‑i` and/or `‑I` as appropriate for the language.         |

---

## 14 · Environment & Exit Codes

| Variable                | Purpose                                       |
|-------------------------|-----------------------------------------------|
| `OPENAI_API_KEY`        | Enables `--ai`.                               |
| `GHCONCAT_DISABLE_AI=1` | Forces the local AI stub (unit tests).        |
| `DEBUG=1`               | Shows Python tracebacks on unexpected errors. |

| Code | Meaning                          |
|------|----------------------------------|
| 0    | Success                          |
| 1    | Fatal error / validation failure |
| 130  | Interrupted via Ctrl‑C           |

---

## 15 · Contribution Guide

* **Style**: `ruff` + `mypy --strict` + the default *black* profile.
* **Tests**: `python -m unittest -v` (or `pytest -q` if you prefer).
* Commit messages: `feat: add wrap‑U flag` (imperative, no trailing period).
* Please open an issue before large refactors – PRs are welcome!

---

## 16 · License

MIT © GAHEOS S.A.

