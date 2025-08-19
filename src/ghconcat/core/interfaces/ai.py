from pathlib import Path
from typing import Optional, Protocol


class AIProcessorProtocol(Protocol):
    """DI-friendly contract for the AI processor used by the engine.

    The protocol mirrors the legacy `_call_openai(...)` bridge by writing
    the result to *out_path*. Implementations must be synchronous and
    raise no exceptions (errors should be encoded in the output file).
    """

    def run(
        self,
        *,
        prompt: str,
        out_path: Path,
        model: str,
        system_prompt: str,
        temperature: Optional[float],
        top_p: Optional[float],
        presence_penalty: Optional[float],
        frequency_penalty: Optional[float],
        seeds_path: Optional[Path],
        max_tokens: Optional[int],
        reasoning_effort: Optional[str],
    ) -> None:
        """Invoke the underlying AI backend with the provided parameters."""