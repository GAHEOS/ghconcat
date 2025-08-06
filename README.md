# ghconcat

> **Hierarchical, language‑agnostic file concatenator · ultra‑deterministic · zero external deps**

`ghconcat` walks your project tree, selects only the files you care about, **strips the noise** (comments, imports,
blank lines, etc.), applies optional line‑range slicing and concatenates the result into a single, reproducible dump.  
Typical use‑cases:

* Giant but clean prompts for LLMs.
* Traceable artefacts in CI/CD.
* Code‑review bundles that stay line‑number‑stable.
* A *source of truth* you can embed in docs or knowledge bases.

---

## 0 · TL;DR – Quick Cheat‑Sheet

```bash
# 1 ─ Local + remote: dump .py + .xml under addons/ & web/, ALSO scrape
#     https://gaheos.com two levels deep, Markdown‑wrap, send to OpenAI:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -F https://gaheos.com -d 2 \
         -u markdown \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Dry‑run: list every discovered HTML reachable from the home page
ghconcat -F https://gaheos.com -s .html -l

# 3 ─ Declarative multi‑step pipeline with contexts
ghconcat -x conf/pipeline.gctx -o build/artifact.txt
````

---

## Table of Contents

1. [Philosophy](#1--philosophy)
2. [Extended Language & Data‑Format Support](#2--extended-language--dataformat-support)
3. [Installation](#3--installation)
4. [Quick Start](#4--quick-start)
5. [CLI Reference](#5--cli-reference)
6. [Conceptual Model](#6--conceptual-model)
7. [Directive Files & Contexts](#7--directive-files--contexts)
8. [Templating & Variables](#8--templating--variables)
9. [AI Gateway](#9--ai-gateway)
10. [Workspaces & Outputs](#10--workspaces--outputs)
11. [Recipes](#11--recipes)
12. [Remote URL Ingestion & Scraping](#12--remote-url-ingestion--scraping)
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
| **Zero dependencies**    | Pure Python ≥ 3.8. The OpenAI bridge is optional (`pip install openai`).             |

---

## 2 · Extended Language & Data‑Format Support

The comment‑rules map covers **30 + popular languages and data formats**, enabling accurate comment stripping and
import/export pruning across a modern full‑stack code base.

| Extension(s)          | Comments recognised       | Import detection          | Export detection          |
|-----------------------|---------------------------|---------------------------|---------------------------|
| `.py`                 | `# …`                     | `import / from`           | —                         |
| `.js`                 | `// …` & `/* … */`        | `import`                  | `export / module.exports` |
| `.ts` / `.tsx`        | idem JS                   | `import`                  | `export`                  |
| `.jsx`                | idem JS                   | `import`                  | `export`                  |
| `.dart`               | idem JS                   | `import`                  | `export`                  |
| `.go`                 | idem JS                   | `import`                  | —                         |
| `.rs`                 | idem JS                   | `use`                     | —                         |
| `.java`               | idem JS                   | `import`                  | —                         |
| `.kt` / `.kts`        | idem JS                   | `import`                  | —                         |
| `.swift`              | idem JS                   | `import`                  | —                         |
| `.c` / `.cpp` / `.cc` | idem JS                   | `#include`                | —                         |
| `.h` / `.hpp`         | idem C/C++                | `#include`                | —                         |
| `.cs`                 | idem JS                   | `using`                   | —                         |
| `.php`                | `//`, `#`, `/* … */`      | `require / include / use` | —                         |
| `.rb`                 | `# …`                     | `require`                 | —                         |
| `.sh` / `.bash`       | `# …`                     | `source / .`              | —                         |
| `.ps1`                | `# …`                     | `Import‑Module`           | —                         |
| `.lua`                | `-- …`                    | `require`                 | —                         |
| `.pl` / `.pm`         | `# …`                     | `use`                     | —                         |
| `.sql`                | `-- …`                    | —                         | —                         |
| `.html` / `.xml`      | `<!-- … -->`              | —                         | —                         |
| `.yml` / `.yaml`      | `# …`                     | —                         | —                         |
| `.css` / `.scss`      | `/* … */` & `// …` (SCSS) | —                         | —                         |
| `.r`                  | `# …`                     | `library()`               | —                         |

---

## 3 · Installation

### 3.1 Core

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 -m pip install .
mkdir -p ~/.bin && cp ghconcat.py ~/.bin/ghconcat && chmod +x ~/.bin/ghconcat
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat --help
```

**Runtime requirements**

* Python ≥ 3.8
* `argparse` and `logging` (stdlib)

### 3.2 Optional extras

| Feature            | Extra package        |
|--------------------|----------------------|
| OpenAI bridge      | `pip install openai` |
| URL fetch/scrape\* | `urllib` (stdlib)    |

\* All networking relies on the Python standard library.

---

## 4 · Quick Start

| Goal                                   | Command                                                                                  |
|----------------------------------------|------------------------------------------------------------------------------------------|
| Concatenate every **.py** under `src/` | `ghconcat -s .py -a src -o dump.txt`                                                     |
| Audit an **Odoo add‑on** clean dump    | `ghconcat -s .py -C -i -a addons/sale_extended`                                          |
| Dry‑run listing                        | `ghconcat -s .py -a addons/sale_extended -l`                                             |
| Wrap & chat with GPT                   | `ghconcat -s .py -s .dart -C -i -a src -u markdown --ai -t tpl/prompt.md -o ai/reply.md` |
| Context pipeline                       | `ghconcat -x ci_pipeline.gctx -o build/ci_bundle.txt`                                    |

---

## 5 · CLI Reference

| Category                | Flag(s) (short / long form)          | Detailed purpose                                                                                                                                                    |
|-------------------------|--------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Location**            | `-w DIR`, `--workdir DIR`            | Root directory where content files are discovered. All relative paths in the current context are resolved from here.                                                |
|                         | `-W DIR`, `--workspace DIR`          | Folder that stores templates, prompts and outputs; defaults to *workdir* if omitted.                                                                                |
| **Discovery**           | `-a PATH`, `--add-path PATH`         | Add a file **or** directory (recursively) to the inclusion set. Repeatable.                                                                                         |
|                         | `-A PATH`, `--exclude-path PATH`     | Exclude an entire directory tree even if it was added by a broader `-a`. Repeatable.                                                                                |
|                         | `-s SUF`, `--suffix SUF`             | Whitelist extension(s) (e.g. `.py`). At least one `-s` turns the suffix filter into “allow-only”. Repeatable.                                                       |
|                         | `-S SUF`, `--exclude-suffix SUF`     | Blacklist extension(s) regardless of origin (local or remote). Repeatable.                                                                                          |
|                         | `-f URL`, `--url URL`                | *Fetch* a single remote resource and cache it as a local file (name preserved or inferred from *Content-Type*). Repeatable.                                         |
|                         | `-F URL`, `--url-scrape URL`         | Depth-limited crawler starting at each seed URL; downloads every linked resource that passes active suffix / exclusion rules. Repeatable.                           |
|                         | `-d N`, `--url-scrape-depth N`       | Maximum recursion depth for `-F` (default **2**; `0` = seed page only).                                                                                             |
|                         | `-D`, `--disable-same-domain`        | Lift same-host restriction when scraping; external domains are followed.                                                                                            |
| **Line slicing**        | `-n NUM`, `--total-lines NUM`        | Keep at most `NUM` lines per file *after* header adjustment.                                                                                                        |
|                         | `-N LINE`, `--start-line LINE`       | Start concatenation at 1-based line `LINE` (can be combined with `-n`).                                                                                             |
|                         | `-m`, `--keep-first-line`            | Always keep the original first line even if slicing starts after it.                                                                                                |
|                         | `-M`, `--no-first-line`              | Force-drop the original first line, overriding an inherited `-m`.                                                                                                   |
| **Clean-up**            | `-c`, `--remove-comments`            | Remove *inline* comments only (language-aware).                                                                                                                     |
|                         | `-C`, `--remove-all-comments`        | Remove both inline **and** full-line comments.                                                                                                                      |
|                         | `-i`, `--remove-import`              | Strip `import` / `require` / `use` statements (Python, JS, Dart, …).                                                                                                |
|                         | `-I`, `--remove-export`              | Strip `export` / `module.exports` declarations (JS, TS, …).                                                                                                         |
|                         | `-b`, `--strip-blank`                | Delete blank lines left after cleaning.                                                                                                                             |
|                         | `-B`, `--keep-blank`                 | Preserve blank lines (overrides an inherited `-b`).                                                                                                                 |
| **Templating & output** | `-t FILE`, `--template FILE`         | Render the raw dump through a Jinja-lite template. Placeholders are expanded afterwards.                                                                            |
|                         | `-o FILE`, `--output FILE`           | Write the final result to disk; path is resolved against *workspace*.                                                                                               |
|                         | `-u LANG`, `--wrap LANG`             | Wrap each file body in a fenced code-block using `LANG` as info-string.                                                                                             |
|                         | `-U`, `--no-wrap`                    | Cancel an inherited wrap in a child context.                                                                                                                        |
|                         | `-h`, `--header`                     | Emit heavy banner headers (`===== path =====`) the first time each file appears.                                                                                    |
|                         | `-H`, `--no-headers`                 | Suppress headers in the current context.                                                                                                                            |
|                         | `-r`, `--relative-path`              | Show header paths relative to *workdir* (default).                                                                                                                  |
|                         | `-R`, `--absolute-path`              | Show header paths as absolute file-system paths.                                                                                                                    |
|                         | `-l`, `--list`                       | *List mode*: print only discovered file paths, one per line.                                                                                                        |
|                         | `-L`, `--no-list`                    | Disable an inherited list mode.                                                                                                                                     |
|                         | `-e VAR=VAL`, `--env VAR=VAL`        | Define a **local** variable visible only in the current context. Repeatable.                                                                                        |
|                         | `-E VAR=VAL`, `--global-env VAR=VAL` | Define a **global** variable inherited by descendant contexts. Repeatable.                                                                                          |
| **STDOUT control**      | `-O`, `--stdout`                     | Always duplicate the final output to STDOUT, even when `-o` is present. When `-o` is absent at the root context, streaming to STDOUT already happens automatically. |
| **AI bridge**           | `--ai`                               | Send the rendered text to OpenAI Chat; reply is written to `-o` (or a temp file) and exposed as `{_ia_ctx}` for templates.                                          |
|                         | `--ai-model NAME`                    | Select chat model (default **o3**).                                                                                                                                 |
|                         | `--ai-temperature F`                 | Sampling temperature (ignored for *o3*).                                                                                                                            |
|                         | `--ai-top-p F`                       | Top-p nucleus sampling value.                                                                                                                                       |
|                         | `--ai-presence-penalty F`            | Presence-penalty parameter.                                                                                                                                         |
|                         | `--ai-frequency-penalty F`           | Frequency-penalty parameter.                                                                                                                                        |
|                         | `--ai-system-prompt FILE`            | System prompt file (placeholder-aware).                                                                                                                             |
|                         | `--ai-seeds FILE`                    | JSONL seed messages to prime the chat.                                                                                                                              |
| **Batch / contexts**    | `-x FILE`, `--directives FILE`       | Execute a directive file containing `[context]` blocks. Each `-x` starts an isolated environment. Repeatable.                                                       |
| **Miscellaneous**       | `--upgrade`                          | Self-update *ghconcat* from the official repository into `~/.bin`.                                                                                                  |
|                         | `--help`                             | Show integrated help and exit.                                                                                                                                      |

**Hints**

* A trailing `·` in the original flag list means the option **can be repeated** (all repeatable flags are explicitly
  noted above).
* Any positional token that does **not** start with `-` is automatically expanded to `-a <token>`.
* Any value-taking flag can be neutralised in a child context by passing the literal `none` (e.g. `-t none`).
* All log messages (INFO / ERROR) are emitted to **stderr**; redirect with `2>/dev/null` if you need a clean dump on
  STDOUT.

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

`‑e/-E` variables and context aliases can be interpolated **in any later stage**.

---

## 7 · Directive Files & Contexts

### 7.1 Syntax

```gctx
# Global defaults
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

* Each `[name]` starts a **child context** inheriting flags.
* Scalar flags override; list flags append; booleans stick once enabled.
* Non‑inherited: `-o`, `-U`, `-L`, `--ai`.

### 7.2 Automatic `‑a` expansion

Inside the file and on the CLI, any token **not starting with `‑`** becomes `‑a TOKEN`.
This lets you mix paths and flags naturally.

---

## 8 · Templating & Variables

| Placeholder source                    | Availability                                |
|---------------------------------------|---------------------------------------------|
| `{ctx}`                               | Final output of context `ctx`               |
| `{_r_ctx}` / `{_t_ctx}` / `{_ia_ctx}` | Raw / templated / AI‑reply of `ctx`         |
| `{ghconcat_dump}`                     | Concatenation of all contexts (root only)   |
| `$VAR`                                | Environment substitution inside flag values |
| `‑e foo=BAR`                          | Local variable                              |
| `‑E foo=BAR`                          | Global variable                             |

In templates, escape braces with `{{`/`}}` to print a literal `{}`.

---

## 9 · AI Gateway

| Aspect        | Detail                                                                                     |
|---------------|--------------------------------------------------------------------------------------------|
| Activation    | `--ai` and `OPENAI_API_KEY`                                                                |
| Default model | `o3`                                                                                       |
| Prompt source | Rendered dump + optional system prompt (`--ai-system-prompt`) + JSONL seeds (`--ai-seeds`) |
| Output        | Written to `‑o` (or temp file) and exposed as `{_ia_ctx}`                                  |
| Disable stub  | `GHCONCAT_DISABLE_AI=1` produces `"AI‑DISABLED"`                                           |

---

## 10 · Workspaces & Outputs

* `‑w` – where files are discovered.
* `‑W` – where templates, prompts and outputs live (defaults to `‑w`).
* Relative paths are resolved against the current context’s `‑w`/`‑W`.

---

## 11 · Recipes

<details>
<summary>11.1 Diff‑friendly dump for code‑review</summary>

```bash
# main branch
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# feature branch
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary>11.2 “Source‑of‑truth” Markdown</summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary>11.3 Context pipeline with AI post‑processing</summary>

```gctx
[concat]
-w .
-a src
-s .py -C -i
-o concat.out.md

[humanize]
-a workspace/concat.out.md
-t tpl/humanize.md
--ai
-o human.out.md

[qa]
-W qa_workspace
-a workspace/human.out.md
-t tpl/qa_check.md
--ai
-o report.md
```

```bash
ghconcat -x pipeline.gctx
```

</details>

<details>
<summary>11.4 Remote + local bundle</summary>

```bash
ghconcat -a src -s .py \
         -F https://gaheos.com/docs -d 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

---

## 12 · Remote URL Ingestion & Scraping

| Flag     | Behaviour                                                                               |
|----------|-----------------------------------------------------------------------------------------|
| `-f URL` | Single fetch. File saved in `.ghconcat_urlcache`; name inferred if needed.              |
| `-F URL` | Depth‑limited crawler; follows links in HTML; honours suffix filters **during** crawl.  |
| `-d N`   | Maximum depth (default 2, `0` = no links).                                              |
| `-D`     | Follow links across domains.                                                            |
| Logs     | `✔ fetched …` / `✔ scraped … (d=N)` messages on **stderr**. Silence with `2>/dev/null`. |

---

## 13 · Troubleshooting

| Symptom                | Hint                                                     |
|------------------------|----------------------------------------------------------|
| Empty dump             | Verify `‑a` paths and suffix filters.                    |
| ChatGPT timeout        | Check network, quota or prompt size (> 128 k tokens?).   |
| `{var}` unresolved     | Define with `‑e`/`‑E` or ensure context alias exists.    |
| Duplicate headers      | Don’t mix `‑h` and header lines inside custom templates. |
| Imports still present  | Use `‑i` and/or `‑I` appropriate for the language.       |
| Too many fetched files | Tighten `-s`/`-S` filters or reduce `-d`.                |

---

## 14 · Environment & Exit Codes

| Variable              | Purpose                                |
|-----------------------|----------------------------------------|
| `OPENAI_API_KEY`      | Enables `--ai`.                        |
| `GHCONCAT_DISABLE_AI` | `1` forces stub (no network).          |
| `DEBUG`               | `1` prints Python traceback on errors. |

| Code | Meaning              |
|------|----------------------|
| 0    | Success              |
| 1    | Fatal error          |
| 130  | Interrupted (Ctrl‑C) |

---

## 15 · Contribution Guide

* Style: `ruff` + `mypy --strict` + *black* default.
* Tests: `python -m unittest -v` (or `pytest -q`).
* Commit format: `feat: add wrap‑U flag` (imperative, no final period).
* For large refactors open an issue first – contributions welcome!

---

## 16 · License

Distributed under the **GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later)**.

Copyright © 2025 GAHEOS S.A.  
Copyright © 2025 Leonardo Gavidia Guerra

See the [`LICENSE`](./LICENSE) file for the complete license text.
