from __future__ import annotations

"""
Minimal SDK surface decoupled from the CLI.

Exports:
  * `_call_openai`: stable adapter used by the engine; tests patch this symbol.
  * `_perform_upgrade`: CLI-upgrade hook, also patched from tests.

New (optional):
  - If GHCONCAT_AI_META=1 is set, write a sidecar JSON with `usage` and
    `finish_reason` next to the AI output file. This is opt-in and does not
    affect existing tests.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ghconcat")


def _call_openai(
    prompt: str,
    out_path: Path,
    *,
    model: str,
    system_prompt: str,
    temperature: float | None,
    top_p: float | None,
    presence_pen: float | None,
    freq_pen: float | None,
    seeds_path: Optional[Path],
    timeout: int = 1800,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
) -> None:
    if os.getenv("GHCONCAT_DISABLE_AI") == "1":
        out_path.write_text("AI-DISABLED", encoding="utf-8")
        return
    if not os.getenv("OPENAI_API_KEY"):
        out_path.write_text("⚠ OpenAI disabled", encoding="utf-8")
        return
    try:
        from ghconcat.ai.ai_client import OpenAIClient
    except Exception as exc:  # pragma: no cover - defensive
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")
        return

    client = OpenAIClient(logger=logger)
    try:
        out = client.generate_chat_completion(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            presence_penalty=presence_pen,
            frequency_penalty=freq_pen,
            seeds_path=seeds_path,
            timeout=timeout,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        out_path.write_text(out, encoding="utf-8")

        # Optional: write sidecar metadata for usage/finish_reason
        if os.getenv("GHCONCAT_AI_META") == "1":
            meta = {
                "usage": client.last_usage or {},
                "finish_reason": client.last_finish_reason,
            }
            sidecar = out_path.with_suffix(out_path.suffix + ".meta.json")
            try:
                sidecar.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            except Exception:
                # Non-fatal; ignore metadata write failures
                pass
    except Exception as exc:  # pragma: no cover - defensive
        out_path.write_text(f"⚠ OpenAI error: {exc}", encoding="utf-8")


def _perform_upgrade() -> None:
    import stat

    tmp = Path(tempfile.mkdtemp(prefix="ghconcat_up_"))
    dest = Path.home() / ".bin" / "ghconcat"
    repo = "git@github.com:GAHEOS/ghconcat.git"
    try:
        subprocess.check_call(
            ["git", "clone", "--depth", "1", repo, str(tmp)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        src = next(tmp.glob("**/ghconcat.py"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
        logger.info("✔ Updated → %s", dest)
    except Exception as exc:
        raise SystemExit(f"Upgrade failed: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    raise SystemExit(0)