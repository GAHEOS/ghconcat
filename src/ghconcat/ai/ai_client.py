import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import openai
except ModuleNotFoundError:
    openai = None


@dataclass(frozen=True)
class ModelSpec:
    """Static capabilities for a model family or exact model."""
    family: str
    reasoning: bool
    endpoint: str  # 'chat' or 'responses'
    supports_temperature: bool
    supports_top_p: bool
    supports_penalties: bool
    supports_logit_bias: bool
    context_window: Optional[int]
    default_max_output_tokens: int


class OpenAIClient:
    """Thin wrapper around OpenAI SDK with conservative defaults."""

    _REASONING_PREFIXES = ('o1', 'o3', 'o4', 'gpt-5')
    _CHAT_PREFIXES = ('gpt-4o', 'gpt-5-chat')
    _CTX_4O = 128000
    _CTX_5_CHAT = 128000

    # Static registry for model families (normalized).
    _MODEL_SPEC_REGISTRY: Dict[str, ModelSpec] = {
        'gpt-5-chat': ModelSpec(
            family='gpt-5-chat',
            reasoning=False,
            endpoint='chat',
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=_CTX_5_CHAT,
            default_max_output_tokens=4096,
        ),
        'gpt-5': ModelSpec(
            family='gpt-5',
            reasoning=True,
            endpoint='responses',
            supports_temperature=False,
            supports_top_p=False,
            supports_penalties=False,
            supports_logit_bias=False,
            context_window=None,
            default_max_output_tokens=4096,
        ),
        'gpt-4o': ModelSpec(
            family='gpt-4o',
            reasoning=False,
            endpoint='chat',
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=_CTX_4O,
            default_max_output_tokens=4096,
        ),
        'o-series': ModelSpec(
            family='o-series',
            reasoning=True,
            endpoint='responses',
            supports_temperature=False,
            supports_top_p=False,
            supports_penalties=False,
            supports_logit_bias=False,
            context_window=None,
            default_max_output_tokens=4096,
        ),
        'generic-chat': ModelSpec(
            family='generic-chat',
            reasoning=False,
            endpoint='chat',
            supports_temperature=True,
            supports_top_p=True,
            supports_penalties=True,
            supports_logit_bias=True,
            context_window=None,
            default_max_output_tokens=1024,
        ),
    }

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        project: Optional[str] = None,
    ) -> None:
        self._log = logger or logging.getLogger('ghconcat.ai')
        self._api_key = api_key or os.getenv('OPENAI_API_KEY', '')
        self._base_url = base_url or os.getenv('OPENAI_BASE_URL') or None
        self._organization = organization or os.getenv('OPENAI_ORG') or None
        self._project = project or os.getenv('OPENAI_PROJECT') or None

        if openai is None:
            self._client = None
        else:
            self._client = openai.OpenAI(
                api_key=self._api_key or None,
                base_url=self._base_url,
                organization=self._organization,
                project=self._project,
            )

    def generate_chat_completion(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str = '',
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        seeds_path: Optional[Path] = None,
        timeout: int = 1800,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """Generate a completion using either chat or responses with safe caps."""
        if self._client is None or not self._api_key:
            self._log.warning('OpenAI SDK/API key not available.')
            return '⚠ OpenAI disabled'

        spec = self._resolve_model_spec(model)
        messages = self._build_messages(system_prompt, seeds_path, prompt)
        desired_max = self._resolve_max_tokens(spec, max_tokens)
        safe_max = self._prevalidate_and_clamp_tokens(spec, model, messages, desired_max)

        try:
            if spec.endpoint == 'responses':
                eff = (reasoning_effort or os.getenv('GHCONCAT_AI_REASONING_EFFORT') or 'medium').lower().strip()
                if eff not in {'low', 'medium', 'high'}:
                    eff = 'medium'
                payload: Dict[str, Any] = {
                    'model': model,
                    'input': messages,
                    'max_output_tokens': safe_max,
                    'timeout': timeout,
                    'reasoning': {'effort': eff},
                }
                rsp = self._client.responses.create(**payload)
                return self._extract_text(rsp) or ''

            # Chat endpoint:
            payload = {'model': model, 'messages': messages, 'timeout': timeout, 'max_tokens': safe_max}
            if spec.supports_temperature and temperature is not None:
                payload['temperature'] = temperature
            if spec.supports_top_p and top_p is not None:
                payload['top_p'] = top_p
            if spec.supports_penalties and presence_penalty is not None:
                payload['presence_penalty'] = presence_penalty
            if spec.supports_penalties and frequency_penalty is not None:
                payload['frequency_penalty'] = frequency_penalty

            rsp = self._client.chat.completions.create(**payload)
            return self._extract_text(rsp) or ''
        except Exception as exc:
            self._log.error('OpenAI error: %s', exc)
            return f'⚠ OpenAI error: {exc}'

    def _resolve_model_spec(self, model: str) -> ModelSpec:
        """Resolve a ModelSpec from the static registry using friendly rules."""
        m = (model or '').lower().strip()
        if m.startswith('gpt-5-chat'):
            return self._MODEL_SPEC_REGISTRY['gpt-5-chat']
        if m.startswith('gpt-5'):
            return self._MODEL_SPEC_REGISTRY['gpt-5']
        if m.startswith('gpt-4o'):
            return self._MODEL_SPEC_REGISTRY['gpt-4o']
        if m.startswith(self._REASONING_PREFIXES):
            return self._MODEL_SPEC_REGISTRY['o-series']
        return self._MODEL_SPEC_REGISTRY['generic-chat']

    def _build_messages(self, system_prompt: str, seeds_path: Optional[Path], user_prompt: str) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        if seeds_path and seeds_path.exists():
            for line in seeds_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and {'role', 'content'} <= set(obj.keys()):
                        role = str(obj['role'])
                        content = str(obj['content'])
                        messages.append({'role': role, 'content': content})
                    else:
                        messages.append({'role': 'user', 'content': line.strip()})
                except json.JSONDecodeError:
                    messages.append({'role': 'user', 'content': line.strip()})
        messages.append({'role': 'user', 'content': user_prompt})
        return messages

    def _resolve_max_tokens(self, spec: ModelSpec, explicit: Optional[int]) -> int:
        if isinstance(explicit, int) and explicit > 0:
            return explicit
        env_val = os.getenv('GHCONCAT_AI_MAX_TOKENS')
        if env_val:
            try:
                n = int(env_val)
                if n > 0:
                    return n
            except ValueError:
                self._log.warning('Invalid GHCONCAT_AI_MAX_TOKENS=%r; ignoring.', env_val)
        return spec.default_max_output_tokens

    def _prevalidate_and_clamp_tokens(self, spec: ModelSpec, model: str, messages: List[Dict[str, str]], desired_max: int) -> int:
        if not spec.context_window:
            return desired_max
        used = self._estimate_tokens(messages, model)
        available_for_output = max(1, spec.context_window - used)
        if desired_max > available_for_output:
            self._log.warning(
                'max tokens reduced: requested=%d, available=%d (model=%s, ctx=%s)',
                desired_max,
                available_for_output,
                model,
                spec.context_window,
            )
            return available_for_output
        return desired_max

    def _estimate_tokens(self, messages: Iterable[Dict[str, str]], model: str) -> int:
        text = '\n'.join((str(m.get('role', '')) + ': ' + str(m.get('content', '')) for m in messages))
        try:
            import tiktoken  # type: ignore
            try:
                enc = tiktoken.encoding_for_model(model)
            except Exception:
                enc = tiktoken.get_encoding('cl100k_base')
            return len(enc.encode(text))
        except Exception:
            pass
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _extract_text(api_result: Any) -> str:
        txt = getattr(api_result, 'output_text', None)
        if isinstance(txt, str) and txt.strip():
            return txt
        try:
            choices = getattr(api_result, 'choices', None)
            if choices and choices[0].message and choices[0].message.content:
                return str(choices[0].message.content)
        except Exception:
            pass
        try:
            out = getattr(api_result, 'output', None)
            if isinstance(out, list):
                chunks: List[str] = []
                for item in out:
                    content = getattr(item, 'content', None)
                    if isinstance(content, list):
                        for c in content:
                            val = getattr(c, 'text', None)
                            if val:
                                chunks.append(str(val))
                if chunks:
                    return '\n'.join(chunks)
        except Exception:
            pass
        return str(api_result or '').strip()