from __future__ import annotations
"""
Utilities to build OpenAI-style chat messages.

This module centralizes the logic for composing the messages array used by
both the ExecutionEngine (for token estimation) and OpenAIClient (for actual
API calls). Centralizing this logic eliminates duplication and ensures that
both sites stay behavior-identical.

Behavioral contract (must remain stable for tests):
- Optional system message first (if provided).
- Optional seed messages read from a JSONL file. Each line can be:
  * a JSON object with at least {"role": "...", "content": "..."}
  * a free text line, which is treated as a user message
- The final user message (the "prompt") is appended at the end.

Refactor note:
- Import `json` at module level to avoid repeated imports inside tight loops.
"""

import json as _json
from pathlib import Path
from typing import Dict, List, Optional


def build_chat_messages(*, system_prompt: str, seeds_path: Optional[Path], user_prompt: str) -> List[Dict[str, str]]:
    """Compose chat-style messages for OpenAI-compatible clients.

    Args:
        system_prompt: Optional system content to prepend.
        seeds_path: Optional JSONL file with seed messages; each line can be a
            JSON object with `role` and `content` fields, or free text treated
            as a 'user' message.
        user_prompt: Final user message to append.

    Returns:
        List of dicts with 'role' and 'content' keys in the expected order.
    """
    messages: List[Dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if seeds_path and seeds_path.exists():
        for line in seeds_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = _json.loads(line)
                if isinstance(obj, dict) and {"role", "content"} <= set(obj.keys()):
                    messages.append({"role": str(obj["role"]), "content": str(obj["content"])})
                else:
                    messages.append({"role": "user", "content": line.strip()})
            except Exception:
                messages.append({"role": "user", "content": line.strip()})

    messages.append({"role": "user", "content": user_prompt})
    return messages