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
"""

from pathlib import Path
from typing import Dict, List, Optional


def build_chat_messages(
    *,
    system_prompt: str,
    seeds_path: Optional[Path],
    user_prompt: str,
) -> List[Dict[str, str]]:
    """Compose a list of chat messages for OpenAI-like APIs.

    Args:
        system_prompt: Optional system prompt; ignored if empty.
        seeds_path: Optional path to a JSONL file with seed messages.
            Each non-empty line is either:
              - a JSON object with keys {"role", "content"}; or
              - plain text treated as a user message.
        user_prompt: The final user-supplied content.

    Returns:
        A list of {"role": str, "content": str} dictionaries in the order
        expected by chat completion APIs.
    """
    messages: List[Dict[str, str]] = []

    # System message first, when provided.
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Optional seeds JSONL.
    if seeds_path and seeds_path.exists():
        for line in seeds_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                import json as _json  # Local import to avoid mandatory dependency.
                obj = _json.loads(line)
                if isinstance(obj, dict) and {"role", "content"} <= set(obj.keys()):
                    messages.append(
                        {"role": str(obj["role"]), "content": str(obj["content"])}
                    )
                else:
                    messages.append({"role": "user", "content": line.strip()})
            except Exception:
                # Be defensive: fallback to user role for non-JSON lines.
                messages.append({"role": "user", "content": line.strip()})

    # Final user message is always appended.
    messages.append({"role": "user", "content": user_prompt})
    return messages