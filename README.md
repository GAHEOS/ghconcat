# ghconcat

> **Multi‑language file concatenator with hierarchical batching, line‑range slicing, advanced clean‑up,
> OpenAI off‑loading and rock‑solid determinism – all in one pure‑Python script.**

`ghconcat` walks your project tree, selects just the files you care about, **strips the noise**, optionally
slices by line range and concatenates everything into a single, reproducible dump.  
Use that dump for code‑review diffs, as a large‑context window for LLMs, to feed static‑analysis tools or to build
traceable artefacts in CI.

---

## 0 · TL;DR – Quick Cheat‑Sheet

```bash
# 1 ─ 100‑line summary of every .py & .xml under addons/ and web/, Markdown‑wrapped,
#     routed through OpenAI and saved in ai/reply.md:
ghconcat -g py -g xml -C -i -n 100 \
         -a addons -a web \
         -t ai/prompt.tpl \
         --ai --ai-model o3 \
         -o ai/reply.md

# 2 ─ Same discovery rules, but list **paths only** (dry‑run):
ghconcat -g py -g xml -a addons -l

# 3 ─ “CI bundle” that stitches three independent jobs together:
ghconcat -X conf/ci_backend.gcx \
         -X conf/ci_frontend.gcx \
         -X conf/ci_assets.gcx \
         -o build/ci_bundle.txt
````

---

## Table of Contents

1. [Philosophy](#1--philosophy)
2. [Feature Matrix](#2--feature-matrix)
3. [Installation](#3--installation)
4. [Quick Start](#4--quick-start)
5. [Full CLI Reference](#5--full-cli-reference)
6. [Conceptual Model](#6--conceptual-model)
7. [Directive Files `‑x` & `‑X`](#7--directive-files-x--x)
8. [Templating & Variables](#8--templating--variables)
9. [ChatGPT Gateway](#9--chatgpt-gateway)
10. [Batching & Hierarchical Contexts](#10--batching--hierarchical-contexts)
11. [Output Strategies & Markdown Wrapping](#11--output-strategies--markdown-wrapping)
12. [Path Handling & Header Semantics](#12--path-handling--header-semantics)
13. [Environment Variables & Exit Codes](#13--environment-variables--exit-codes)
14. [Self‑Upgrade & Version Pinning](#14--selfupgrade--version-pinning)
15. [Troubleshooting](#15--troubleshooting)
16. [Recipes](#16--recipes)
17. [Security & Privacy Notes](#17--security--privacy-notes)
18. [Performance Tips](#18--performance-tips)
19. [Contribution Guide](#19--contribution-guide)
20. [License](#20--license)

---

## 1 · Philosophy

| Principle                    | Rationale                                                                                                 |
|------------------------------|-----------------------------------------------------------------------------------------------------------|
| **Single‑command context**   | Stop opening a dozen files just to understand a PR – the dump is human‑readable and line‑number stable.   |
| **Deterministic output**     | Same input ⇒ same dump. Perfect for CI diffing and caching.                                               |
| **Composable orchestration** | Mix quick one‑liners, inline bundles (`‑x`) and hierarchical jobs (`‑X`) without sacrificing readability. |
| **Read‑only safety**         | The tool never writes to your sources; everything happens in memory or to a chosen `‑o` path.             |
| **AI‑first workflow**        | Seamless bridge to OpenAI with JSONL seeds, system prompts, alias interpolation and timeout protection.   |
| **Zero external deps**       | Pure Python ≥3.8; only the ChatGPT bridge is optional (`pip install openai`).                             |
| **Cross‑platform**           | Linux, macOS, Windows (PowerShell) – no native extensions, no shell tricks.                               |

---

## 2 · Feature Matrix

| Domain               | Highlights                                                                                                                                  |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| **Discovery**        | Recursive walk, path inclusion/exclusion, suffix filter, skip hidden dirs & files, ignore `*.g.dart`, de‑dup headers across contexts.       |
| **Language presets** | `odoo`, `flutter`, plus arbitrary extensions & wildcard mixes (`‑g py -g xml -g .csv`).                                                     |
| **Clean‑up**         | Strip *simple* comments (`‑c`) or *all* comments (`‑C`), imports (`‑i`), exports (`‑I`), optional blank‑line culling (default).             |
| **Slicing**          | Keep first *n* lines (`‑n`), start at arbitrary line (`‑N`), preserve line‑1 header even if sliced (`‑H`).                                  |
| **Batching**         | Inline bundles (`‑x`) and hierarchical jobs (`‑X`) with OR/concat inheritance rules, `none` sentinel to disable upstream flags.             |
| **Templating**       | `{dump_data}` placeholder + unlimited aliases (`‑O`), local (`‑e`) & global (`‑E`) env vars, workspace scoping and `$ENV_VAR` substitution. |
| **LLM Bridge**       | OpenAI models, 1800s timeout, JSONL seeds, automatic fenced blocks (`‑u lang`), prompt size cut‑off (\~128k tokens).                        |
| **Output**           | Optional `‑o` file, dry‑run (`‑l`), absolute/relative headers (`‑p`), no‑header mode (`‑P`), Markdown wrap (`‑u`).                          |
| **Self‑upgrade**     | Atomic `--upgrade` that clones *ghconcat* from GitHub to `~/.bin` and marks it executable.                                                  |

---

## 3 · Installation

> Requires Python **3.8+**. The ChatGPT gateway is optional.

### Linux / macOS

```bash
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python3 setup.py install    # or: pip install .
mkdir -p ~/.bin && cp ghconcat.py ~/.bin/ghconcat && chmod +x ~/.bin/ghconcat
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
ghconcat -h
```

### Enable ChatGPT Gateway

```bash
pip install openai
export OPENAI_API_KEY=sk-********************************
```

---

## 4 · Quick Start

| Task                                                                     | Command                                                                                                                  |
|--------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Dump every **Python** file under `src/` into `dump.txt`                  | `ghconcat -g py -a src -o dump.txt`                                                                                      |
| Audit an **Odoo add‑on**, strip comments & imports, keep first 100 lines | `ghconcat -g odoo -C -i -n 100 -a addons/sale_extended`                                                                  |
| Dry‑run (paths only)                                                     | `ghconcat -g odoo -a addons/sale_extended -l`                                                                            |
| Send compressed dump to ChatGPT using a template, save reply             | `ghconcat -g py -g dart -C -i -a src -t tpl/prompt.md --ai -o reply.md`                                                  |
| Merge three independent batch jobs                                       | `ghconcat -X ci_backend.gcx -X ci_frontend.gcx -X ci_assets.gcx -o build/ci.txt`                                         |
| Wrap each chunk in fenced Markdown `js` blocks                           | `ghconcat -g js -u js -a web -o docs/src_of_truth.md`                                                                    |
| Generate an architectural summary with commit hash interpolation         | `ghconcat -g py -g dart -C -i -a src -t ai/summarise.tpl -e version=$(git rev-parse --short HEAD) --ai -o ai/summary.md` |

---

## 5 · Full CLI Reference

Flags are grouped thematically; repeatable flags are marked **·**.

| Category                | Flags & Parameters                                                                  | Description                                                                |
|-------------------------|-------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| **Batch / Nesting**     | `‑x FILE`·                                                                          | Inline bundle – expands before parsing.                                    |
|                         | `‑X FILE`·                                                                          | Hierarchical context – parsed with inheritance rules (see §10).            |
| **Location**            | `‑w DIR`                                                                            | Workdir / root for relative paths (default = CWD).                         |
|                         | `‑W DIR`                                                                            | Workspace for templates, prompts and outputs (default = workdir).          |
|                         | `‑a PATH`·                                                                          | Include file or directory.                                                 |
|                         | `‑A PATH`·                                                                          | Exclude file or directory (prefix match).                                  |
|                         | `‑s SUF`· / `‑S SUF`·                                                               | Include / exclude files by suffix.                                         |
| **Language Filters**    | `‑g LANG`· / `‑G LANG`·                                                             | Include / exclude language/extension or preset (`odoo`, `flutter`).        |
| **Line‑range**          | `‑n NUM`                                                                            | Keep at most NUM lines.                                                    |
|                         | `‑N LINE`                                                                           | 1‑based starting line (used with or without `‑n`).                         |
|                         | `‑H`                                                                                | Preserve original line 1 even if sliced out.                               |
| **Clean‑Up**            | `‑c` / `‑C`                                                                         | Remove simple / all comments.                                              |
|                         | `‑i` / `‑I`                                                                         | Strip import / export statements.                                          |
|                         | `‑B`                                                                                | Keep blank lines (default = drop).                                         |
| **Output & Templating** | `‑t FILE` / `‑t none`                                                               | Template with `{dump_data}`; `none` disables upstream template.            |
|                         | `‑o FILE`                                                                           | Write final output to FILE.                                                |
|                         | `‑O ALIAS`                                                                          | Expose current dump/render as `${ALIAS}` to parent contexts and templates. |
|                         | `‑u LANG` / `‑u none`                                                               | Wrap each chunk in fenced `LANG` blocks; `none` cancels inheritance.       |
|                         | `‑l`                                                                                | List paths only (no body).                                                 |
|                         | `‑p` / `‑P`                                                                         | Absolute headers / no headers at all.                                      |
| **Variables**           | `‑e VAR=VAL`·                                                                       | Local env var (current context only).                                      |
|                         | `‑E VAR=VAL`·                                                                       | Global env var (propagates to children).                                   |
| **AI Gateway**          | `--ai`                                                                              | Enable ChatGPT call.                                                       |
|                         | `--ai-model M`                                                                      | OpenAI model (default `o3`).                                               |
|                         | `--ai-system-prompt FILE`                                                           | Custom system prompt (template‑aware).                                     |
|                         | `--ai-seeds FILE/none`                                                              | JSONL seeds; `none` disables inheritance.                                  |
|                         | `--ai-temperature`, `--ai-top-p`, `--ai-presence-penalty`, `--ai-frequency-penalty` | Optional model parameters (ignored on models with fixed temperature).      |
| **Misc**                | `--upgrade`                                                                         | Self‑upgrade from GitHub.                                                  |
|                         | `-h`                                                                                | Help.                                                                      |

> *Any value flag can be neutralised in a child context by passing `none`.*

---

## 6 · Conceptual Model

```
roots (‑a)  →  path & suffix filters (‑A/‑s/‑S)  →  language set (‑g/‑G)  →  clean‑up  →  slicing  →  dump
                                                                                 │
                                                                                 ▼
                                             templating (‑t)  →  ChatGPT (--ai)  →  output (‑o / alias)
```

---

## 7 · Directive Files `‑x` & `‑X`

### 7.1 Inline Bundles `‑x`

* Parsed **before** `argparse` → can define new flags or override CLI.
* Multiple `‑x` are concatenated in order.

```gcx
# defaults.gcx
-g odoo
-c -i -n 120
-a addons -a tests
```

```bash
ghconcat -x defaults.gcx -G js -a docs -o dump.txt
```

### 7.2 Hierarchical Contexts `‑X`

* File is tokenised exactly like CLI (one context per line).
* Inheritance rules:

| Attribute type | Merge rule                       |
|----------------|----------------------------------|
| Booleans       | Logical **OR** (cannot be unset) |
| Lists          | Parent + Child (concatenate)     |
| Scalars        | Child overrides                  |
| Non‑inherited  | `‑o`, `‑O`, `--ai`, `‑t`         |

* Bracket syntax `[alias]` inside a `.gcx` line creates an **inline sub‑context** equivalent to `‑X __ctx:alias`.

---

## 8 · Templating & Variables

* Always available placeholder: **`{dump_data}`**.
* Every `‑O ALIAS` makes `{ALIAS}` available downstream.
* `‑e` / `‑E` inject custom key‑values; use `$VAR` inside any directive file for env expansion.
* Templates are resolved against `--workspace` first, then `--workdir`.

---

## 9 · ChatGPT Gateway

| Aspect            | Detail                                                                                             |
|-------------------|----------------------------------------------------------------------------------------------------|
| Activation        | `--ai` flag; requires `OPENAI_API_KEY`.                                                            |
| System prompt     | `--ai-system-prompt FILE` – template‑aware.                                                        |
| Seeds             | JSONL lines with `{ "role": "...", "content": "..." }`; inherited unless `--ai-seeds none`.        |
| Timeout           | 1800s wall‑clock.                                                                                  |
| Token safety      | Hard stop at ≈128k tokens (≈350k chars) to avoid 413 errors.                                       |
| Model params      | Temperature, top‑p, presence & frequency penalties (ignored on fixed‑temp models such as `o3`).    |
| Output handling   | Reply is written to `‑o` if provided, else to a temp file; alias (if any) is updated **after** AI. |
| Error propagation | Network/quota/format errors → non‑zero exit, original dump untouched.                              |

---

## 10 · Batching & Hierarchical Contexts

* You can combine unlimited `‑X` jobs at level 0; nesting deeper than one level is **forbidden** to prevent recursion.
* Global header de‑duplication works automatically when **no template** is applied at the top level.
* Child contexts may independently call ChatGPT, set their own templates, or override env vars.

---

## 11 · Output Strategies & Markdown Wrapping

* **Relative headers** (default) are ideal for diffs, because paths stay stable when the repo moves.
* Use `‑p` for absolute paths when converting the dump to HTML with hyperlinks.
* `‑u LANG` wraps each chunk in fenced \`\`\`\`LANG\`\`\` blocks; good for ChatGPT, Markdown docs, or static sites.
* Combine `‑l` with `‑p` to obtain a clean manifest of absolute paths for external tooling.
* `‑P` suppresses headers entirely – useful when the dump will be embedded inside another template that already names
  files.

---

## 12 · Path Handling & Header Semantics

* Hidden files/dirs (`.foo`, `.git`, `.private`) are skipped unless explicitly included.
* `*.g.dart` is ignored by default (generated code); override with `‑s` / `‑S` if needed.
* `‑H` duplicates original line 1 **only** when it would be otherwise excluded by slicing rules.
* Passing `none` to any value flag in a child context disables its inherited value (`‑n none`, `‑u none`, etc.).

---

## 13 · Environment Variables & Exit Codes

| Variable         | Purpose                                       |
|------------------|-----------------------------------------------|
| `OPENAI_API_KEY` | Enables `--ai` gateway.                       |
| `DEBUG=1`        | Shows Python tracebacks on unexpected errors. |

| Code | Meaning                          |
|------|----------------------------------|
| 0    | Success                          |
| 1    | Fatal error / validation failure |
| 130  | Interrupted by user (`Ctrl‑C`)   |

---

## 14 · Self‑Upgrade & Version Pinning

Run:

```bash
ghconcat --upgrade
```

The script clones the latest stable tag to `~/.bin/ghconcat` atomically and makes it executable.
Automate with `cron(8)`:

```
0 6 * * MON ghconcat --upgrade >/var/log/ghconcat-up.log 2>&1
```

For hermetic builds, pin a specific version in your CI by exporting `GHCONCAT_VERSION` and checking it inside your
pipeline.

---

## 15 · Troubleshooting

| Symptom                                                 | Resolution                                                    |
|---------------------------------------------------------|---------------------------------------------------------------|
| *“after apply all filters no active extension remains”* | Your `‑g`/`‑G` set filtered everything – adjust the mix.      |
| Empty dump or missing files                             | Check roots (`‑a`), suffix filter (`‑s`/`‑S`), hidden dirs.   |
| ChatGPT “hangs” or times out                            | Network? API key? Prompt <128k tokens?                        |
| “flag expects VAR=VAL”                                  | Fix the syntax in `‑e` or `‑E`.                               |
| Seeds file ignored after `--ai-seeds none`              | That is expected – inheritance was intentionally disabled.    |
| Headers appear twice                                    | Use templates **or** rely on global de‑duplication, not both. |

---

## 16 · Recipes

<details>
<summary><strong>16.1 Diff‑friendly dump for code‑review</strong></summary>

```bash
# main branch
ghconcat -g odoo -C -i -a addons/sale -o /tmp/base.txt

# feature branch (checkout first)
ghconcat -g odoo -C -i -a addons/sale -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>16.2 Absolute‑path audit in server‑side CI</strong></summary>

```bash
ghconcat -g py -g xml -C -i -a src -p -u text -o build/audit.txt
```

Convert `audit.txt` to HTML with anchors pointing to your repository browser.

</details>

<details>
<summary><strong>16.3 Pre‑commit hook: lint, concatenate staged files, open in pager</strong></summary>

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
<summary><strong>16.4 One‑liner to produce a “source‑of‑truth” Markdown file</strong></summary>

```bash
ghconcat -g dart -g js -C -i -a lib -a web -u js -o docs/source_of_truth.md
```

</details>

<details>
<summary><strong>16.5 Generate an OpenAPI spec summary with seeded context</strong></summary>

```bash
ghconcat -g yml -g yaml -C -a api \
         -t ai/openapi.tpl \
         --ai --ai-seeds ai/seeds.jsonl \
         -o ai/openapi_overview.md
```

</details>

<details>
<summary><strong>16.6 Aggregate back‑end, front‑end and assets in one artefact</strong></summary>

```bash
ghconcat -X ci_backend.gcx \
         -X ci_frontend.gcx \
         -X ci_assets.gcx \
         -o build/ci_bundle.txt
```

</details>

---

## 17 · Security & Privacy Notes

* `ghconcat` never transmits your source code unless `--ai` is enabled.
* When using `--ai`, **every byte** of the rendered prompt is sent to OpenAI.
  Evaluate your IP policy and regulatory constraints before enabling.
* The OpenAI API key is read **only** from `OPENAI_API_KEY`; no local caching.
* Use network‑level egress policies in CI if you need to block external calls.
* The tool exits with a clear error if the prompt exceeds the model’s hard limit.

---

## 18 · Performance Tips

* Combine `‑c` and `‑i` to reduce prompt size by \~35 % on Python‑heavy repos.
* Prefer presets (`-g odoo`) over many individual extensions; the internal set is cached.
* Running inside a container? Mount the workspace (`‑W`) on a tmpfs for faster I/O.
* When using `‑X` contexts, group files logically to maximise header de‑duplication.

---

## 19 · Contribution Guide

1. **Style**`ruff` + `mypy --strict` + black defaults.
2. **Tests**`pytest -q` or `python -m unittest -v`.
3. **Commits**`<scope>: <subject>` (imperative, no trailing period).
4. **Sign‑off**`git config --global user.signingkey …`.
5. **PRs** welcome! Please open an issue before large rewrites.

---

## 20 · License

**MIT** – see `LICENSE` for the full text.
