# ghconcat

> **Multi‑language file concatenator with Odoo & Flutter presets, advanced slicing, batch orchestration and ChatGPT
off‑loading — all in one self‑contained Python script.**

`ghconcat` walks your project tree, cherry‑picks the files you really care about, **strips the noise**, optionally
slices by line‑range, and concatenates the result into a deterministic, human‑readable dump.  
Use the dump for code‑review diffs, as a context window for an LLM, or as a “single‑file source of truth” in automated
audits.

---

## 0 · TL;DR

```bash
# 1 – 100‑line summary of every Python & XML file inside addons/ + web/, ready for ChatGPT:
ghconcat -g py -g xml -C -i -n 100 \
         -a addons -a web \
         -K SUMMARY=1.0 -t ai/prompt.tpl -Q -o ai/reply.md   # -K (env var), -o optional but recommended

# 2 – Same dump, but **only list the file paths** (no body)
ghconcat -g py -g xml -a addons -l

# 3 – Create a “CI bundle” by merging three independent jobs
ghconcat \
  -X conf/ci_backend.bat \
  -X conf/ci_frontend.bat \
  -X conf/ci_assets.bat \
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
7. [Directive Files `-x` & `-X`](#7--directive-files-x--x)
    1. [Inline Flag Bundles `-x`](#71-x--inline-flag-bundles)
    2. [Batch Jobs `-X`](#72-x--batch-jobs)
8. [Recipes](#8--recipes)
9. [ChatGPT Gateway](#9--chatgpt-gateway)
10. [Self‑Upgrade](#10--selfupgrade)
11. [Environment & Exit Codes](#11--environment--exit-codes)
12. [Troubleshooting](#12--troubleshooting)
13. [FAQ](#13--faq)
14. [Contributing](#14--contributing)
15. [License](#15--license)

---

## 1 · Philosophy

| Principle                    | Rationale                                                         |
|------------------------------|-------------------------------------------------------------------|
| **One‑command context**      | No need to open fifteen files in your editor just to “grasp” a PR |
| **Deterministic dump**       | Same input ⇒ same output → perfect for CI diffs                   |
| **Composable orchestration** | Inline (`‑x`) bundles, batch (`‑X`) jobs, flag inheritance        |
| **Read‑only safety**         | Never rewrites your sources; everything happens in memory         |
| **AI‑first workflow**        | Built‑in hand‑off (`‑Q`) with a production‑grade system prompt    |

---

## 2 · Feature Matrix

| Domain           | Highlights                                                                                     |
|------------------|------------------------------------------------------------------------------------------------|
| **Discovery**    | Recursive walk, path & directory exclusions, suffix filter, **hidden‑file skip**               |
| **Language set** | Mix & match inclusions (`‑g py`,`‑g xml`) & exclusions (`‑G js`). Presets: `odoo`, `flutter`   |
| **Clean‑up**     | Strip comments (`‑c` ➜ simple, `‑C` ➜ all), imports (`‑i`), exports (`‑I`), blank lines (`‑s`) |
| **Slicing**      | Keep *n* lines (`‑n`), arbitrary ranges (`‑n` + `‑N`), header preservation (`‑H`)              |
| **Batching**     | Flag bundles (`‑x`) and hierarchical jobs (`‑X`) with inheritance rules                        |
| **Templating**   | `{dump_data}` placeholder, custom aliases (`‑k ALIAS`) and env vars (`‑K VAR=VAL`)             |
| **LLM Bridge**   | Robust 1800 s timeout, JSON‑safe wrapping, automatic fenced code blocks (`‑u`)                 |
| **Output**       | `‑o` file optional; without it the dump is returned to callers (library mode)                  |
| **Header paths** | **Relative by default**; add `‑p/‑‑absolute‑path` for absolute headers                         |
| **Self‑upgrade** | `--upgrade` pulls the latest commit from GitHub in one atomic copy                             |

## 3 · Installation

> ghconcat is pure-Python ≥ 3.8 and has **no external runtime dependencies**  
> (ChatGPT features are optional – see below).

### Unix-like (Linux / macOS)

```bash
# 1. Clone the repo
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat

# 2. Install the package (system-wide or into a venv)
python3 setup.py install  # uses setuptools

# 3. Copy the launcher to a personal bin dir
mkdir -p ~/.bin
cp ghconcat.py ~/.bin/ghconcat
chmod +x ~/.bin/ghconcat

# 4. Add ~/.bin to your PATH (if not already there)
echo 'export PATH="$HOME/.bin:$PATH"' >> ~/.bashrc    # bash
source ~/.bashrc   # reload, or restart the shell

# 5. Smoke test
ghconcat -h
````

### Windows (PowerShell)

```powershell
# 1. Clone and install
git clone https://github.com/GAHEOS/ghconcat.git
cd ghconcat
python setup.py install

# 2. Copy script to a user bin directory
$Bin="$env:USERPROFILE\bin"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Copy-Item ghconcat.py "$Bin\ghconcat.py"

# 3. Add that directory to PATH (persistent for current user)
[Environment]::SetEnvironmentVariable('Path', "$Bin;$env:Path", 'User')

# 4. Alias for convenience (current session)
Set-Alias ghconcat python "$Bin\ghconcat.py"

# 5. Verify
ghconcat -h
```

### Optional: ChatGPT integration

```bash
pip install openai
export OPENAI_API_KEY=sk-********************************
# or, on Windows PowerShell:
# [Environment]::SetEnvironmentVariable('OPENAI_API_KEY','sk-********************************','User')
```

> **Tip:** To keep ghconcat global while working inside virtual-envs, leave `~/.bin` ahead of the venv in your `PATH`, or symlink the launcher into each environment’s `bin/` directory.


## 4 · Quick Start

| Task                                                                             | Command                                                                          |
|----------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| Dump every **Python** file under `src/` into `dump.txt`                          | `ghconcat -g py -a src -o dump.txt`                                              |
| Audit an **Odoo add‑on**, strip **all** comments & imports, keep first 100 lines | `ghconcat -g odoo -C -i -n 100 -a addons/sale_extended`                          |
| Dry‑run (*list only*)                                                            | `ghconcat -g odoo -a addons/sale_extended -l`                                    |
| Send compressed dump to ChatGPT using `tpl/prompt.md`, save reply to `reply.md`  | `ghconcat -g py -g dart -C -i -a src -t tpl/prompt.md -Q -o reply.md`            |
| Merge three independent batch files                                              | `ghconcat -X ci_backend.bat -X ci_frontend.bat -X ci_assets.bat -o build/ci.txt` |

---

## 5 · Full CLI Reference

*(flags are grouped by theme; repeatable flags are explicitly marked)*

| Flags                       | Purpose / Notes                                                            |
|-----------------------------|----------------------------------------------------------------------------|
| **Batch orchestration**     |                                                                            |
| `‑x FILE`                   | *Inline bundle* – expand flags from FILE **before** parsing                |
| `‑X FILE` *(repeatable)*    | *Batch job* – run FILE as an independent job and merge its dump            |
| **File discovery**          |                                                                            |
| `‑a PATH` *(repeatable)*    | Add root PATH (file or directory)                                          |
| `‑r DIR`                    | Logical root for resolving relatives                                       |
| `‑w DIR`                    | Workspace (output destination base; default=`cwd`)                         |
| `‑e DIR` *(repeatable)*     | Recursively exclude directory DIR                                          |
| `‑E PAT` *(repeatable)*     | Exclude any path containing substring PAT                                  |
| `‑S SUF` *(repeatable)*     | Only include files ending with suffix SUF                                  |
| **Language set**            |                                                                            |
| `‑g LANG` *(repeatable)*    | Include language / extension (`py`, `xml`, `.csv`, preset `odoo`)          |
| `‑G LANG` *(repeatable)*    | Exclude language / extension                                               |
| **Slicing**                 |                                                                            |
| `‑n NUM`                    | Keep NUM lines *starting at* `first_line` (`‑N`) or from top               |
| `‑N LINE`                   | 1‑based line where slicing starts                                          |
| `‑H`                        | Duplicate original line 1 if excluded by slicing                           |
| **Cleaning**                |                                                                            |
| `‑c` / `‑C`                 | Remove simple / all comments                                               |
| `‑i` / `‑I`                 | Remove `import` / `export` statements                                      |
| `‑s`                        | Keep blank lines (otherwise dropped)                                       |
| **Output & templating**     |                                                                            |
| `‑o FILE`                   | Output file (optional; if omitted the dump is only returned by the API)    |
| `‑u LANG`                   | Wrap each chunk in fenced Markdown «`LANG`»                                |
| `‑t FILE`                   | Template containing `{dump_data}` placeholders                             |
| `‑k ALIAS`                  | Expose this dump as `{ALIAS}` to the **parent** template (max 1 per level) |
| `‑K VAR=VAL` *(repeatable)* | Extra key‑value for template interpolation                                 |
| `‑l`                        | List files only (no body)                                                  |
| `‑p` / `‑‑absolute‑path`    | Print absolute paths in headers (default = relative to `--root`)           |
| **AI gateway**              |                                                                            |
| `‑Q`                        | Send rendered dump to ChatGPT                                              |
| `‑m MODEL`                  | OpenAI model (default `o3`)                                                |
| `‑M FILE`                   | Custom system prompt                                                       |
| **Misc**                    |                                                                            |
| `‑U`                        | Self‑upgrade from GitHub                                                   |
| `‑L` ES \| EN               | CLI / prompt language (ES default)                                         |
| `‑h`                        | Help                                                                       |

---

## 6 · Conceptual Model

```
┌──────────────┐    ┌─────────────┐    ┌─────────────────┐
│ 1· Roots     │ →  │ 2· Filters  │ →  │ 3· Language set │
└──────────────┘    └─────────────┘    └─────────────────┘
        ↓                      ↓                    ↓
  (walk filesystem)   (suffix / path check)   (include / exclude)
        └─────────────┬───────────────┬─────────────────┘
                      ↓
          4· Clean‑up pipeline  →  5· Slicing  → 6· Dump
                      ↓
            7· Template / ChatGPT
```

---

## 7 · Directive Files `‑x` & `‑X`

### 7.1 `‑x` – Inline Flag Bundles

*Loaded **before** `argparse`*, therefore can add *new* flags and override user input.

```text
# defaults.dct
-g odoo        # preset
-c -i          # clean‑up
-n 120         # slice
-a addons -a tests
```

```bash
ghconcat -x defaults.dct -G js -a docs -o dump.txt
```

### 7.2 `‑X` – Batch Jobs

Each **non‑empty line** is parsed with full CLI semantics:

```text
# ci_backend.bat
-g py -a addons -e .git
-g py -g xml -a migrations -C -i
```

Flag inheritance:

| Type       | Behaviour                  |
|------------|----------------------------|
| Booleans   | OR‑merged                  |
| Lists      | Concatenated               |
| Singletons | Child overrides            |
| Forbidden  | `‑x`, `‑t`, `‑o`, AI flags |

---

## 8 · Recipes

<details>
<summary><strong>8.1 Story‑diff for Code‑Review</strong></summary>

```bash
# baseline (main)
ghconcat -g odoo -C -i -a addons/sale -o /tmp/base.txt

# PR branch
ghconcat -g odoo -C -i -a addons/sale -o /tmp/head.txt

diff -u /tmp/base.txt /tmp/head.txt | less -R
```

</details>

<details>
<summary><strong>8.2 Automatic Architectural Summary (EN)</strong></summary>

```bash
ghconcat -g py -g dart -C -i -s -a src \
         -t ai/summarise.tpl \
         -K version=$(git rev-parse --short HEAD) \
         -Q -o ai/summary.md -L EN
```

</details>

---

## 9 · ChatGPT Gateway

| Aspect        | Detail                                                                             |
|---------------|------------------------------------------------------------------------------------|
| System prompt | Opinionated, bilingual; override with `‑M my_prompt.txt`                           |
| Placeholders  | Always substitute `{dump_data}` plus any `‑K VAR=VAL` or `‑k alias`                |
| Token safety  | Max ≈ 128 k tokens (≈ 350 k chars) – aborts early with a clear message if exceeded |
| Timeout       | 1800 wall clock                                                                    |
| Failure modes | Network / quota / format errors ⇒ **non‑zero exit**, local dump untouched          |

---

## 10 · Self‑Upgrade

```bash
ghconcat --upgrade   # atomic; copies to ~/.bin/ghconcat (change in source to tweak)
```

Add to crontab:

```
0 6 * * MON  ghconcat --upgrade >/var/log/ghconcat-upgrade.log 2>&1
```

---

## 11 · Environment & Exit Codes

| Var / Value      | Meaning                                     |
|------------------|---------------------------------------------|
| `OPENAI_API_KEY` | Enables all `‑Q` features                   |
| `DEBUG=1`        | Show Python tracebacks on unexpected errors |

| Code | Meaning                             |
|------|-------------------------------------|
| 0    | Success                             |
| 1    | Fatal error (bad flag, IO issue, …) |
| 130  | User cancelled (`Ctrl‑C`)           |

---

## 12 · Troubleshooting

| Symptom                                                       | Fix                                                        |
|---------------------------------------------------------------|------------------------------------------------------------|
| *“After applying --exclude‑lang no active extension remains”* | Review your `‑g/‑G` set; you filtered **everything**       |
| Empty dump / missing files                                    | Check roots (`‑a`), suffix filter (`‑S`), hidden directories |
| ChatGPT hangs                                                 | Internet? API key? Dump <128k tokens?                      |
| “Forbidden flag inside ‑X context”                            | Remove `‑o`, `‑t`, AI flags from that batch line           |

---

## 13 · FAQ

<details>
<summary>Can I nest <code>-X</code> inside another <code>-X</code> job?</summary>
No; ghconcat blocks it to avoid accidental recursion.  
Run multiple top‑level `‑X` flags instead.
</details>

<details>
<summary>Why are <code>*.g.dart</code> files excluded?</summary>
They are usually generated; ghconcat ignores them unless you force inclusion
with `‑S .g.dart` or patch the helper inside <code>_collect_files()</code>.
</details>

<details>
<summary>Does the tool run on Windows?</summary>
Yes – it is pure Python 3.8+. Use PowerShell aliases as shown in the installation section.
</details>

---

## 14 · Contributing

* Code style: **PEP8**, `ruff`, `mypy --strict`
* Tests: `pytest -q`
* Commit message: `<scope>: <subject>` (no trailing period)
* Sign‑off: `git config --global user.signingkey …`

PRs welcome!

---

## 15 · License

MIT – see `LICENSE` for full text.

