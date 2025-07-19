# ghconcat

> **Multi‑language file concatenator with Odoo / Flutter presets, advanced slicing, batch orchestration, and ChatGPT hand‑off.**

`ghconcat` collects, cleans, and concatenates heterogeneous source files—Python, Dart, XML, CSV, JS, YAML, you name it—into a single, well‑structured dump. The dump can be inspected by humans, diffed by CI, or sent directly to ChatGPT for automated reviews and refactors.

---

## Table of Contents

1. [Philosophy](#1--philosophy)
2. [Feature Matrix](#2--feature-matrix)
3. [Installation](#3--installation)
4. [Quick Start](#4--quick-start)
5. [Full CLI Reference](#5--full-cli-reference)
6. [Conceptual Model](#6--conceptual-model)
7. [Directive Files Deep Dive](#7--directive-files-deep-dive)
   1. [Inline (`-x`) – Flag Bundles](#71-inline-x--flag-bundles)
   2. [Batch (`-X`) – Independent Jobs](#72-batch-x--independent-jobs)
8. [Recipes & Workflows](#8--recipes--workflows)
   1. [Code‑review “story diff”](#81-codereview-story-diff)  
   2. [Pre‑LLM compression + summary](#82-prellm-compression--summary)
9. [ChatGPT Integration](#9--chatgpt-integration)
10. [Upgrade Path](#10--upgrade-path)
11. [Environment Variables & Exit Codes](#11--environment-variables--exit-codes)
12. [Troubleshooting](#12--troubleshooting)
13. [FAQ](#13--faq)
14. [Contributing](#14--contributing)
15. [License](#15--license)


---

## 1 · Philosophy

* **One‑command context** End the scavenger hunt across back‑end, front‑end, and data files.
* **Deterministic by design** Byte‑for‑byte reproducibility → perfect for code reviews and CI diffs.
* **Composable orchestration** Inline/batch directives + flag inheritance let you script complex jobs.
* **Zero noise** Every clean‑up switch is explicit; your code is never mutated in place.
* **AI‑ready** A dedicated gateway pushes the dump to ChatGPT, obeying a robust system prompt.

---

## 2 · Feature Matrix

| Area                 | Abilities                                                                                          |
| -------------------- |----------------------------------------------------------------------------------------------------|
| Discovery            | Recursive walk, per‑path exclusion, directory blacklists, suffix filters                           |
| Extensions           | Include (`--py`, `--xml`, …) & exclude (`--no-*`) switches, plus presets (`--odoo`)                |
| Clean‑up             | Strip comments (`-c` / `-C`), imports (`-i`), exports (`-I`), blank lines (`-S`)                   |
| Slicing              | Head/tail (`‑n`), arbitrary ranges (`‑n` + `‑N`), header preservation (`‑H`)                       |
| Directive files      | *Inline* `‑x` (flag bundles) and *batch* `‑X` (multiple jobs, hierarchical inheritance)            |
| Internationalisation | CLI messages and ChatGPT prompt in **English** or **Spanish** (`‑l`)                               |
| AI off‑loading       | Template‑driven prompt injection, assistant output capture, 120 s timeout, graceful error handling |
| Maintenance          | One‑shot GitHub upgrade (`--upgrade`), hidden tracebacks unless `DEBUG=1`                          |

---

## 3 · Installation

Unix‑like systems:

```bash
git clone https://github.com/GAHEOS/ghconcat.git
sudo cp ghconcat/ghconcat.py /usr/local/bin/ghconcat   # or any dir in $PATH
sudo chmod +x /usr/local/bin/ghconcat
ghconcat -h
```

Windows (PowerShell):

```powershell
git clone https://github.com/GAHEOS/ghconcat.git
Copy-Item ghconcat/ghconcat.py $env:USERPROFILE\bin\ghconcat.py
Set-Alias ghconcat python $env:USERPROFILE\bin\ghconcat.py
ghconcat -h
```

> **Optional (AI)**
>
> ```bash
> pip install openai
> export OPENAI_API_KEY=sk-********************************
> ```

---

## 4 · Quick Start

Concatenate **all** Python files under `src/` into `dump.txt`:

```bash
ghconcat --py -a src -f dump.txt
```

Audit an Odoo add‑on, strip **all** comments and imports, keep only first 100 lines:

```bash
ghconcat --odoo -C -i -n 100 -a addons/sale_extended
```

Dry‑run (list candidate files only):

```bash
ghconcat --odoo -t -a addons/sale_extended
```

---

## 5 · Full CLI Reference

| Short | Long / Group                   | Type | Default    | Description                                                | Example                 |
| ----- | ------------------------------ | ---- | ---------- | ---------------------------------------------------------- | ----------------------- |
| `-x`  | — *Pre*                        | FILE | —          | Expand extra flags from FILE **before** normal parsing.    | `-x defaults.dct`       |
| `-X`  | — *Pre*                        | FILE | —          | Execute independent batch defined in FILE; merge its dump. | `-X nightly.bat`        |
| `-a`  | — *Filter*                     | PATH | `.`        | Add file/dir to search roots (repeatable).                 | `-a src -a tests`       |
| `-r`  | `--root`                       | DIR  | CWD        | Base directory for resolving relatives.                    | `-r /opt/project`       |
| `-e`  | — *Filter*                     | PAT  | —          | Skip paths containing substring PAT.                       | `-e .git`               |
| `-E`  | — *Filter*                     | DIR  | —          | Recursively exclude directory DIR.                         | `-E node_modules`       |
| `-p`  | — *Filter*                     | SUF  | —          | Only include files ending with SUF.                        | `-p _test.py`           |
| `-k`  | — *Filter*                     | EXT  | —          | Whitelist extra extension (with dot).                      | `-k .md`                |
| `-f`  | — *Misc*                       | FILE | `dump.txt` | Output destination.                                        | `-f audit.txt`          |
| `-n`  | — *Slice*                      | INT  | —          | Head length (alone) or start line (with `-N`).             | `-n 150`                |
| `-N`  | — *Slice*                      | INT  | —          | End line (inclusive), needs `-n`.                          | `-n 10 -N 50`           |
| `-H`  | — *Slice*                      | FLAG | false      | Preserve first non‑blank line even if out of range.        | `-H`                    |
| `-t`  | — *Behav.*                     | FLAG | false      | Output headers only (no body).                             | `-t`                    |
| `-c`  | — *Clean*                      | FLAG | false      | Remove simple comments.                                    | `-c`                    |
| `-C`  | — *Clean*                      | FLAG | false      | Remove all comments (supersedes `-c`).                     | `-C`                    |
| `-S`  | — *Clean*                      | FLAG | false      | Keep blank lines.                                          | `-S`                    |
| `-i`  | — *Clean*                      | FLAG | false      | Remove `import` statements.                                | `-i`                    |
| `-I`  | — *Clean*                      | FLAG | false      | Remove `export` / `module.exports`.                        | `-I`                    |
| —     | `--odoo`                       | FLAG | false      | Shortcut: include `.py`, `.xml`, `.csv`, `.js`.            | `--odoo`                |
| —     | `--py`                         | FLAG | off        | Include Python sources.                                    | `--py`                  |
| —     | `--no-py`                      | FLAG | off        | Exclude Python even if included.                           | `--no-py`               |
| …     | (same for Dart/XML/CSV/JS/YML) |      |            |                                                            |                         |
| —     | `--ia-prompt`                  | FILE | —          | Template containing `{dump_data}` for ChatGPT.             | `--ia-prompt ask.tpl`   |
| —     | `--ia-output`                  | FILE | —          | File for ChatGPT reply.                                    | `--ia-output answer.md` |
| —     | `--upgrade`                    | FLAG | false      | Pull latest version from GitHub and replace local copy.    | `--upgrade`             |
| `-l`  | `--lang`                       | CODE | `ES`       | UI language: `ES` or `EN` (case‑insensitive).              | `-l EN`                 |
| `-h`  | `--help`                       | FLAG | —          | Show help and exit.                                        | —                       |

---

## 6 · Conceptual Model

1. **Roots** – Starting points (`‑a`) scanned recursively.
2. **Extension set** – Built from inclusion/exclusion flags and `‑k`.
3. **Filters** – Path patterns, blacklisted dirs, filename suffixes.
4. **Clean‑up pipeline** – Comment stripping → import/export removal → blank‑line pruning.
5. **Slicing** – Optional head/tail extraction with header keep.
6. **Dump assembly** – File sections are prefixed by `===== /abs/path =====`.
7. **Post‑processing** – Optional ChatGPT hand‑off.

---

## 7 · Directive Files Deep Dive

### 7.1 Inline (`‑x`) – Flag Bundles

Purpose: share a common flag set across multiple invocations.

**Syntax essentials**

* Parsed **before** normal CLI; last flag wins.
* Supports comments (`#` or trailing `//`) and multi‑value `-a`.

`defaults.dct`:

```text
--odoo           // multi‑language preset
-c               # strip simple comments
-n 120           // keep only first 120 lines
-a addons        // root 1
-a tests         // root 2
```

Use it:

```bash
ghconcat -x defaults.dct -k .md -a docs
```

Here, `.md` files and `docs/` are appended *after* expanding `defaults.dct`.

---

### 7.2 Batch (`‑X`) – Independent Jobs

Each non‑comment line triggers a **separate** concatenation job.
Flags inheritance works as follows:

1. Parent (main CLI) → child (batch line) **OR**‑merged for booleans.
2. List flags (`-e`, `-E`, `-p`, `-k`) are concatenated.
3. Child may negate inherited booleans (`--no-*`).
4. Nested `‑X` inside a batch is **forbidden** (guards against recursion).

Example `ci.bat` (realistic):

```text
# Base flags for every job:
--odoo -c -i -H

# ─── Backend unit tests ─────────────────────────────────────────────
-a addons             // root
-p _test.py           // suffix
--no-js --no-xml      // speed up

# ─── Web assets: keep comments for ESLint review ────────────────────
-a web/static/src
--no-py --no-csv
-S                    // keep blank lines
-I                    // but drop exports
```

Run:

```bash
ghconcat -X ci.bat -f ci_bundle.txt
```

The resulting `ci_bundle.txt` merges both jobs in the order defined.

---

## 8 · Recipes & Workflows

### 8.1 Code‑review "story diff"

```bash
ghconcat --odoo -C -i -a addons/new_feature -f story.txt
ghconcat --odoo -C -i -a addons/new_feature -p _old.py -f baseline.txt
diff -u baseline.txt story.txt > review.patch
```

### 8.2 Pre‑LLM compression + summary

```bash
ghconcat --py --dart --xml -C -i -I -S -a src \
         --ia-prompt ai/summarise.tpl \
         --ia-output ai/summary.md \
         -l EN
```

Template `summarise.tpl`:

```text
Summarise the following code changes focusing on architectural impact:

{dump_data}
```

---

## 9 · ChatGPT Integration

* **Round‑trip safety** – Remote errors are caught; local dump is never lost.
* **Prompt design** – Use `{dump_data}` placeholder; everything else is yours.
* **Language swap** – `‑l ES` replaces only the word **English** with **Spanish** in the system prompt so code stays English‑compliant.
* **Timeout** – Hard‑coded to 120 s; set `DEBUG=1` to see raw SDK traces.

---

## 10 · Upgrade Path

Automated weekly cron:

```bash
0 4 * * 1  ghconcat --upgrade >> /var/log/ghconcat-upgrade.log 2>&1
```

Manual fallback:

```bash
ghconcat --upgrade   # always safe; compares hashes before overwrite
```

---

## 11 · Environment Variables & Exit Codes

| Variable         | Effect                                |
| ---------------- | ------------------------------------- |
| `OPENAI_API_KEY` | Enables ChatGPT features.             |
| `DEBUG=1`        | Show tracebacks on unexpected errors. |

| Exit | Meaning                               |
| ---- | ------------------------------------- |
| 0    | Success                               |
| 1    | Fatal error (bad flags, IO issues, …) |
| 130  | Keyboard interrupt (`Ctrl‑C`)         |

---

## 12 · Troubleshooting

| Symptom                               | Fix                                                                         |
| ------------------------------------- |-----------------------------------------------------------------------------|
| *“No active extension after filters”* | Review `--no-*` flags or add `-k .ext`.                                     |
| Dump is empty                         | Did you forget to `‑a` a root? Is suffix filter too strict?                 |
| ChatGPT request hangs                 | Check internet, API key, and that dump size ≤ 128 k tokens (≈ 350 k chars). |

---

## 13 · FAQ

<details>
<summary>Can I nest <code>-X</code> inside another batch?</summary>
No. Nested batches are blocked to avoid infinite loops. Use multiple top‑level
`‑X` invocations if you need complex orchestration.
</details>

<details>
<summary>How do I include generated code like <code>.g.dart</code>?</summary>
Those files are ignored by default. Add `-p .g.dart` to force inclusion or
clone and patch the regexp inside `collect_files()`.
</details>

---

## 14 · Contributing

* Style: **PEP 8**, `ruff`, `mypy --strict`.
* Tests: `pytest -q`.
* Commit message format: `<scope>: <subject>` (no trailing period).
* Sign your work (`git config --global user.signingkey …`).

---

## 15 · License

MIT. See `LICENSE` for the legalese.
