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
#     https://gaheos.com two levels deep **AND** a single file from GitHub,
#     Markdown-wrap, send to OpenAI:
ghconcat -s .py -s .xml -C -i -n 120 \
         -a addons -a web \
         -g https://github.com/GAHEOS/ghconcat^dev/src/ghconcat.py \
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
11. [Remote URL & Git Ingestion](#11--remote-url--git-ingestion)
  - [11.1 · Remote Git repositories (`-g` / `-G`)](#111--remote-git-repositories--g---g)
12. [Recipes](#12--recipes)
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

| Category                | Flag(s) (short / long form)                                   | Detailed purpose                                                                                                                                                    |
|-------------------------|---------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Location**            | `-w DIR`, `--workdir DIR`                                     | Root directory where content files are discovered. All relative paths in the current context are resolved from here.                                                |
|                         | `-W DIR`, `--workspace DIR`                                   | Folder that stores templates, prompts and outputs; defaults to *workdir* if omitted.                                                                                |
| **Discovery**           | `-a PATH`, `--add-path PATH`                                  | Add a file **or** directory (recursively) to the inclusion set. Repeatable.                                                                                         |
|                         | `-A PATH`, `--exclude-path PATH`                              | Exclude an entire directory tree even if it was added by a broader `-a`. Repeatable.                                                                                |
|                         | `-s SUF`, `--suffix SUF`                                      | Whitelist extension(s) (e.g. `.py`). At least one `-s` turns the suffix filter into “allow-only”. Repeatable.                                                       |
|                         | `-S SUF`, `--exclude-suffix SUF`                              | Blacklist extension(s) regardless of origin (local or remote). Repeatable.                                                                                          |
|                         | `-f URL`, `--url URL`                                         | *Fetch* a single remote resource and cache it as a local file (name preserved or inferred from *Content-Type*). Repeatable.                                         |
|                         | `-F URL`, `--url-scrape URL`                                  | Depth-limited crawler starting at each seed URL; downloads every linked resource that passes active suffix / exclusion rules. Repeatable.                           |
|                         | `-g SPEC`, `--git-path SPEC` `SPEC = URL[^BRANCH][/SUBPATH]`. | **Include sources from a remote *Git* repo**. If *BRANCH* is omitted, default branch is used; if *SUBPATH* is omitted the whole repo is scanned.                    |                                                                                                                 
|                         | `-G SPEC`, `--git-exclude SPEC`                               | Exclude *file* or *subtree* inside a repo previously added with `-g`.                                                                                               |
|                         | `-d N`, `--url-scrape-depth N`                                | Maximum recursion depth for `-F` (default **2**; `0` = seed page only).                                                                                             |
|                         | `-D`, `--disable-same-domain`                                 | Lift same-host restriction when scraping; external domains are followed.                                                                                            |
| **Line slicing**        | `-n NUM`, `--total-lines NUM`                                 | Keep at most `NUM` lines per file *after* header adjustment.                                                                                                        |
|                         | `-N LINE`, `--start-line LINE`                                | Start concatenation at 1-based line `LINE` (can be combined with `-n`).                                                                                             |
|                         | `-m`, `--keep-first-line`                                     | Always keep the original first line even if slicing starts after it.                                                                                                |
|                         | `-M`, `--no-first-line`                                       | Force-drop the original first line, overriding an inherited `-m`.                                                                                                   |
| **Clean-up**            | `-c`, `--remove-comments`                                     | Remove *inline* comments only (language-aware).                                                                                                                     |
|                         | `-C`, `--remove-all-comments`                                 | Remove both inline **and** full-line comments.                                                                                                                      |
|                         | `-i`, `--remove-import`                                       | Strip `import` / `require` / `use` statements (Python, JS, Dart, …).                                                                                                |
|                         | `-I`, `--remove-export`                                       | Strip `export` / `module.exports` declarations (JS, TS, …).                                                                                                         |
|                         | `-b`, `--strip-blank`                                         | Delete blank lines left after cleaning.                                                                                                                             |
|                         | `-B`, `--keep-blank`                                          | Preserve blank lines (overrides an inherited `-b`).                                                                                                                 |
| **Templating & output** | `-t FILE`, `--template FILE`                                  | Render the raw dump through a Jinja-lite template. Placeholders are expanded afterwards.                                                                            |
|                         | `-o FILE`, `--output FILE`                                    | Write the final result to disk; path is resolved against *workspace*.                                                                                               |
|                         | `-u LANG`, `--wrap LANG`                                      | Wrap each file body in a fenced code-block using `LANG` as info-string.                                                                                             |
|                         | `-U`, `--no-wrap`                                             | Cancel an inherited wrap in a child context.                                                                                                                        |
|                         | `-h`, `--header`                                              | Emit heavy banner headers (`===== path =====`) the first time each file appears.                                                                                    |
|                         | `-H`, `--no-headers`                                          | Suppress headers in the current context.                                                                                                                            |
|                         | `-r`, `--relative-path`                                       | Show header paths relative to *workdir* (default).                                                                                                                  |
|                         | `-R`, `--absolute-path`                                       | Show header paths as absolute file-system paths.                                                                                                                    |
|                         | `-l`, `--list`                                                | *List mode*: print only discovered file paths, one per line.                                                                                                        |
|                         | `-L`, `--no-list`                                             | Disable an inherited list mode.                                                                                                                                     |
|                         | `-e VAR=VAL`, `--env VAR=VAL`                                 | Define a **local** variable visible only in the current context. Repeatable.                                                                                        |
|                         | `-E VAR=VAL`, `--global-env VAR=VAL`                          | Define a **global** variable inherited by descendant contexts. Repeatable.                                                                                          |
| **STDOUT control**      | `-O`, `--stdout`                                              | Always duplicate the final output to STDOUT, even when `-o` is present. When `-o` is absent at the root context, streaming to STDOUT already happens automatically. |
| **AI bridge**           | `--ai`                                                        | Send the rendered text to OpenAI Chat; reply is written to `-o` (or a temp file) and exposed as `{_ia_ctx}` for templates.                                          |
|                         | `--ai-model NAME`                                             | Select chat model (default **o3**).                                                                                                                                 |
|                         | `--ai-temperature F`                                          | Sampling temperature (ignored for *o3*).                                                                                                                            |
|                         | `--ai-top-p F`                                                | Top-p nucleus sampling value.                                                                                                                                       |
|                         | `--ai-presence-penalty F`                                     | Presence-penalty parameter.                                                                                                                                         |
|                         | `--ai-frequency-penalty F`                                    | Frequency-penalty parameter.                                                                                                                                        |
|                         | `--ai-system-prompt FILE`                                     | System prompt file (placeholder-aware).                                                                                                                             |
|                         | `--ai-seeds FILE`                                             | JSONL seed messages to prime the chat.                                                                                                                              |
| **Batch / contexts**    | `-x FILE`, `--directives FILE`                                | Execute a directive file containing `[context]` blocks. Each `-x` starts an isolated environment. Repeatable.                                                       |
| **Miscellaneous**       | `--upgrade`                                                   | Self-update *ghconcat* from the official repository into `~/.bin`.                                                                                                  |
|                         | `--help`                                                      | Show integrated help and exit.                                                                                                                                      |

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

## 11 · Remote URL & **Git** Ingestion

| Flag     | Behaviour                                                                               |
|----------|-----------------------------------------------------------------------------------------|
| `-f URL` | Single fetch. File saved in `.ghconcat_urlcache`; name inferred if needed.              |
| `-F URL` | Depth‑limited crawler; follows links in HTML; honours suffix filters **during** crawl.  |
| `-d N`   | Maximum depth (default 2, `0` = no links).                                              |
| `-D`     | Follow links across domains.                                                            |
| Logs     | `✔ fetched …` / `✔ scraped … (d=N)` messages on **stderr**. Silence with `2>/dev/null`. |

### 11.1 · Remote **Git** repositories (`-g` / `-G`)

| Flag      | Behaviour                                                               |
|-----------|-------------------------------------------------------------------------|
| `-g SPEC` | Shallow-clones the repo into `.ghconcat_gitcache/` (one per SPEC) and   |
|           | adds every file that matches suffix filters. `SPEC` syntax:             |
|           | `URL[^BRANCH][/SUBPATH]` (examples below).                              |
| `-G SPEC` | Excludes a file or directory inside any repo previously added with `-g` |

**Examples**

```bash
# Whole repo, default branch:
ghconcat -g https://github.com/pallets/flask.git -s .py

# Only docs/ directory from main:
ghconcat -g https://github.com/pallets/flask/docs -s .rst

# Single file on a dev branch:
ghconcat -g git@github.com:GAHEOS/ghconcat^dev/src/ghconcat.py -s .py
```

## 12 · Recipes

<details>
<summary>12.1 Diff‑friendly dump for code‑review</summary>

```bash
# main branch
ghconcat -s .py -C -i -a src -o /tmp/base.txt

# feature branch
ghconcat -s .py -C -i -a src -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary>12.2 “Source‑of‑truth” Markdown</summary>

```bash
ghconcat -s .js -s .dart -C -i -a lib -a web \
         -u markdown -h -R \
         -o docs/source_of_truth.md
```

</details>

<details>
<summary>12.3 Context pipeline with AI post‑processing</summary>

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
<summary>12.4 Remote + local bundle</summary>

```bash
ghconcat -a src -s .py \
         -F https://gaheos.com/docs -d 1 -s .html \
         -h -R \
         -o docs/review_bundle.txt
```

</details>

<details>
<summary>12.5 Large‑scale academic literature synthesis pipeline 📚🤖 (one‑shot `‑x`)</summary>

> This recipe demonstrates how **one single directive file** orchestrates an end‑to‑end scholarly workflow powered by
> multiple LLM “personas”.
> We will:
>
> 1. Harvest primary sources from local notes **and** remote open‑access URLs.
> 2. Let a *junior researcher* create the first‑pass synthesis.
> 3. Ask a *senior researcher* to refine it.
> 4. Invite an *academic critic* to challenge the claims.
> 5. Apply a *language editor* to improve clarity and style.
> 6. Call the critic **again** for a final peer‑review.
> 7. Save the polished report for the human team to iterate on.

The whole flow is encoded in **`academic_pipeline.gctx`** (see below).
All intermediate artefacts live inside the *workspace*; every stage can reuse the previous one either through
`-a workspace/<file>` **or** by referencing the context alias in a template (`{junior}`, `{senior}`, …).

#### Run it

```bash
ghconcat -x academic_pipeline.gctx -O
# The final manuscript appears on STDOUT and is also written to workspace/final_report.md
```

---

#### `academic_pipeline.gctx`

```text
// ======================================================================
//  ghconcat academic pipeline – Quantum Computing example
//  All paths that do *not* start with “-” are implicitly “-a <path>”.
// ======================================================================

# Global settings ----------------------------------------------------------------
-w .                                   # project root holding local notes/
-W workspace                         # keep prompts + outputs separate
-E topic="Quantum Computing and Photonics"  # Visible in *all* templates

# -------------------------------------------------------------------------------
# 0 · Gather raw corpus  →  sources                                            //
# -------------------------------------------------------------------------------
[sources]
// Two open‑access papers (HTML render)
-F https://arxiv.org/abs/2303.11366     # Integrated Photonics for Quantum Computing
-F https://arxiv.org/abs/2210.10255     # Boson sampling in the noisy intermediate scale
-d 0

-K                                      # clean text (remove html tags, scripts, etc)
-s .html -C -i -u web-research -h       # clean & wrap
-o sources.md                           # expose as {sources}

[notes]
-a notes/
-s .md -u note -h                       # clean & wrap
-o notes.md                             # expose as {sources}

# -------------------------------------------------------------------------------
# 1 · Junior researcher draft  →  junior                                        //
# -------------------------------------------------------------------------------
[junior]
-a workspace/sources.md                  # feed the corpus
-a workspace/notes.md                    # feed the corpus
-t prompts/junior.md                     # persona prompt (see below)
--ai --ai-model o3                       # cheap deterministic model
-o junior.out.md

# -------------------------------------------------------------------------------
# 2 · Senior researcher pass  →  senior                                         //
# -------------------------------------------------------------------------------
[senior]
-a workspace/junior.out.md
-t prompts/senior.md
--ai --ai-model gpt-4o
-o senior.out.md
-E to_critic=$senior

# -------------------------------------------------------------------------------
# 3 · First academic critique  →  critic1                                       //
# -------------------------------------------------------------------------------
[critic1]
-a workspace/senior.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic1.out.md

# -------------------------------------------------------------------------------
# 4 · Language & style polish  →  redraft                                       //
# -------------------------------------------------------------------------------
[redraft]
-a workspace/critic1.out.md
-t prompts/editor.md
--ai --ai-model gpt-4o
-o redraft.out.md

# -------------------------------------------------------------------------------
# 5 · Final critique after polish  →  critic2                                   //
# -------------------------------------------------------------------------------
[critic2]
-a workspace/redraft.out.md
-t prompts/critic.md
--ai --ai-model gpt-4o
-o critic2.out.md
-E to_critic=$redraft

# -------------------------------------------------------------------------------
# 6 · Bundle for humans  →  final                                               //
# -------------------------------------------------------------------------------
[final]
-a workspace/critic2.out.md
-h -R                                     # add absolute path banner for traceability
-o final_report.md
```

#### Prompt files

> Store these under `prompts/` (relative to the workspace).
> Every template can access:
>
> * `{topic}` – global variable defined with `‑E`.
> * `{sources}`, `{junior}`, `{senior}`, … – context aliases.

##### prompts/junior.md

```markdown
### Role

You are a **junior research associate** preparing an initial literature review on **{topic}**.

### Task

1. Read the raw corpus located in  ```note``` and ```web-research``` markdown code blocks.
2. Extract **key research questions**, **methodologies**, and **major findings**.
3. Output a *numbered outline* (max 1 000 words).

{notes}
{sources}
```

##### prompts/senior.md

```markdown
### Role

You are a **senior principal investigator** mentoring a junior colleague.

### Task

Improve the draft below by:

* Merging redundant points.
* Adding missing seminal works you are aware of.
* Flagging any methodological weaknesses.

Return a revised outline with inline comments where changes were made.

### Web-research background

{source}

### Junior Notes

{notes}

### Draft Outline

{junior}
```

##### prompts/critic.md

```markdown
### Role

You serve on a *blind peer‑review committee*.

### Task

1. Critically evaluate logical coherence, evidential support and novelty claims.
2. Highlight **factual inaccuracies** or missing citations.
3. Grade each section (A–D) and justify the grade in 30 words max.

Document under review:

{to_critic}
```

##### prompts/editor.md

```markdown
### Role

Professional **science copy‑editor**.

### Task

Rewrite the document for clarity, concision and formal academic tone.  
Fix passive‑voice overuse, tighten sentences, and ensure IEEE reference style.

## Critique Summary

{critic1}

## Revised Document

Source (critically reviewed):
{senior}
```

##### notes/note_lab_log_2025-06-03.md

```markdown
# Lab Log – 3 Jun 2025

*Integrated Silicon Nitride Waveguides for On-Chip Entanglement*

## Objective

Test the latest Si₃N₄ waveguide batch (run #Q-0601) for loss, birefringence and two-photon interference visibility.

## Setup

| Item         | Model                                 | Notes          |
|--------------|---------------------------------------|----------------|
| Pump laser   | TOPTICA iBeam-Smart 775 nm            | 10 mW CW       |
| PPLN crystal | Period = 7.5 µm                       | Type-0 SPDC    |
| Chip mount   | Temperature-controlled (25 ± 0.01 °C) | –              |
| Detectors    | SNSPD pair, η≈80 %                    | Jitter ≈ 35 ps |

## Key results

* Propagation loss **1.3 dB ± 0.1 dB cm⁻¹** @ 1550 nm (cut-back).
* HOM dip visibility **91 %** without spectral filtering (best so far).
* No appreciable birefringence within ±0.05 nm tuning range.

> **TODO**: simulate dispersion for 3 cm spirals; schedule e-beam mask adjustments.
```

##### notes/note_conference_summary_QIP2025.md

```markdown
# QIP 2025 – Hot-topic Session Summary

*Tokyo, 27 Jan 2025*

## 1. Boson Sampling Beyond 100 Photons

**Speaker:** Jian-Wei Pan

* Claimed 1 × 10⁻²₃ sampling hardness bound using 144-mode interferometer.
* Introduced time-domain multiplexing scheme; reduces footprint 40 ×.

## 2. Error-Corrected Photonic Qubits

**Speaker:** Stefanie Barz

* Demonstrated **[[4,2,2]]** code on dual-rail qubits with 97 % heralded fidelity.
* Cluster-state growth via fusion-II gates reached 10⁶ physical time-bins.

## 3. NV-Centre to Photon Transduction

**Speaker:** M. Atatüre

* On-chip diamond-SiN evanescent coupling, g≈30 MHz.
* Outlook: deterministic Bell-state delivery at >10 k links.

### Cross-cutting trends

* Integrated PPLN and thin-film LiNbO₃ are **everywhere**.
* Shift from bulk optics toward heterogeneous III-V + SiN platforms.
* Community rallying around **“error mitigation before error correction”** mantra.
```

##### notes/note_review_article_highlights.md

```markdown
# Highlights – Review: *“Photonic Quantum Processors”* (Rev. Mod. Phys. 97, 015005 (2025))

| Section              | Take-away                                                                                                | Open questions                                                    |
|----------------------|----------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Linear-optical gates | Deterministic CNOT remains >90 dB loss-budget dream; hybrid measurement-based approaches most promising. | Can η_det ≥ 95 % SNSPDs plus temporal multiplexing close the gap? |
| Integrated sources   | On-chip χ² micro-rings achieve 300 MHz pair rate at p-pump = 40 mW.                                      | Thermal cross-talk scaling beyond 100 sources?                    |
| Error models         | Dephasing now dominates over loss in tightly confined waveguides.                                        | Need unified benchmarking across foundries.                       |
| Applications         | Near-term advantage in photonic machine-learning inference.                                              | Energy/latency trade-off vs silicon AI accelerators.              |

### Author’s critique

The review glosses over cryo-packaging challenges and the *actual* cost of ultra-low-loss SiN (≤0.5 dB m⁻¹). Include
comparative LCA data in future work.
````

##### What just happened?

| Stage     | Input                         | Template            | AI? | Output (alias)    |
|-----------|-------------------------------|---------------------|-----|-------------------|
| `sources` | Local notes + two ArXiv pages | — (raw concat)      | ✗   | `{sources}`       |
| `junior`  | `sources.md`                  | `junior.md`         | ✔   | `{junior}`        |
| `senior`  | `junior.md`                   | `senior.md`         | ✔   | `{senior}`        |
| `critic1` | `senior.md`                   | `critic.md`         | ✔   | `{critic1}`       |
| `redraft` | `critic1.md`                  | `editor.md`         | ✔   | `{redraft}`       |
| `critic2` | `redraft.md`                  | `critic.md`         | ✔   | `{critic2}`       |
| `final`   | `critic2.md` (no AI)          | — (banner + concat) | ✗   | `final_report.md` |

The final manuscript is **fully traceable**: every intermediate file is preserved, headers show absolute paths, and you
can replay any stage by re‑running its context with different flags or a different model.

Happy researching!

</details>

---

## 13 · Troubleshooting

| Symptom                | Hint                                                            |
|------------------------|-----------------------------------------------------------------|
| Empty dump             | Verify `‑a` paths and suffix filters.                           |
| ChatGPT timeout        | Check network, quota or prompt size (> 128 k tokens?).          |
| `{var}` unresolved     | Define with `‑e`/`‑E` or ensure context alias exists.           |
| Duplicate headers      | Don’t mix `‑h` and header lines inside custom templates.        |
| Imports still present  | Use `‑i` and/or `‑I` appropriate for the language.              |
| Too many fetched files | Tighten `-s`/`-S` filters or reduce `-d`.                       |
| Stale Git clone        | Delete `.ghconcat_gitcache` or run with `--preserve-cache` off. |

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
