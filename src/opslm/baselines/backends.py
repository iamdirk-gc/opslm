"""Provider backends for the LLM system.

A backend turns (system prompt, user message, JSON schema) into a ``Completion``. Everything
provider-specific lives here so ``LLMPredictor`` and the evaluation stay model-agnostic.

Each backend imports its SDK lazily and accepts an injected ``client``, so the package works
without any SDK installed and tests never touch the network.

- ``AnthropicBackend``: Claude via the Anthropic API. Claude on Vertex or Bedrock works by
  passing that platform's client (``AnthropicVertex`` etc.) as ``client``.
- ``OpenAICompatibleBackend``: anything that speaks the OpenAI chat-completions protocol:
  vLLM, Ollama, TGI, Together, OpenRouter, Vertex AI's OpenAI-compatible endpoint, and OpenAI.
  This is the route for open-weight models, base and fine-tuned.
- ``VertexGeminiBackend``: Gemini models on Vertex AI through the Google Gen AI SDK.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol

Finish = Literal["stop", "length", "refused", "other"]


@dataclass(frozen=True)
class Completion:
    text: str | None
    input_tokens: int
    output_tokens: int  # includes reasoning/thinking tokens where the provider bills them
    finish: Finish
    detail: str | None = None


class ChatBackend(Protocol):
    model: str
    label: str  # short unique name used in result files, e.g. "anthropic:claude-opus-5-5:medium"

    def complete(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> Completion: ...

    def describe(self) -> dict[str, Any]: ...


class AnthropicBackend:
    """Claude via the Anthropic SDK. Server-side refusal fallbacks are deliberately not used."""

    def __init__(
        self,
        model: str,
        *,
        effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium",
        client: Any = None,
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.effort = effort
        self.label = f"anthropic:{model}:{effort}"

    def complete(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> Completion:
        # No sampling parameters: current Claude models reject them. Thinking is left at the
        # model default; effort is explicit because defaults differ between models.
        r = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in r.content if b.type == "text"), None)
        finish: Finish = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length",
                          "refusal": "refused"}.get(r.stop_reason, "other")
        detail = None
        if finish == "refused":
            detail = getattr(getattr(r, "stop_details", None), "category", None)
        elif finish == "other":
            detail = str(r.stop_reason)
        return Completion(text, r.usage.input_tokens, r.usage.output_tokens, finish, detail)

    def describe(self) -> dict[str, Any]:
        return {"provider": "anthropic", "model": self.model, "effort": self.effort,
                "server_side_fallbacks": False}


class OpenAICompatibleBackend:
    """Any server speaking the OpenAI chat-completions protocol.

    ``structured`` controls how the JSON answer is requested:
    - ``json_schema``: constrained decoding against the schema (vLLM, recent Ollama, OpenAI).
    - ``json_object``: JSON mode only; the schema is described in the prompt instead.
    - ``none``: plain text; the schema is described in the prompt and the reply is parsed.
    Use the weaker modes for servers or models without constrained decoding.
    """

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float | None = 0.0,
        structured: Literal["json_schema", "json_object", "none"] = "json_schema",
        max_tokens_param: Literal["max_tokens", "max_completion_tokens"] = "max_tokens",
        client: Any = None,
    ) -> None:
        if client is None:
            import openai

            key = api_key or os.environ.get(api_key_env)
            if key is None and base_url:
                key = "EMPTY"  # self-hosted servers usually ignore the key
            client = openai.OpenAI(base_url=base_url, api_key=key)
        self._client = client
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.structured = structured
        self.max_tokens_param = max_tokens_param
        self.label = f"openai-compatible:{model}"

    def complete(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> Completion:
        kwargs: dict[str, Any] = {self.max_tokens_param: max_tokens}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.structured == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "judgment", "strict": True, "schema": schema},
            }
        else:
            if self.structured == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            system = (
                f"{system}\nRespond with a single JSON object and nothing else, matching this "
                f"JSON schema:\n{json.dumps(schema)}"
            )
        r = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **kwargs,
        )
        choice = r.choices[0]
        finish: Finish = {"stop": "stop", "length": "length", "content_filter": "refused"}.get(
            choice.finish_reason, "other"
        )
        detail = None if finish in ("stop", "length") else str(choice.finish_reason)
        usage = r.usage
        return Completion(
            choice.message.content,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
            finish,
            detail,
        )

    def describe(self) -> dict[str, Any]:
        return {"provider": "openai-compatible", "model": self.model, "base_url": self.base_url,
                "temperature": self.temperature, "structured": self.structured}


class VertexGeminiBackend:
    """Gemini on Vertex AI via the Google Gen AI SDK (authenticates with ADC)."""

    _REFUSED: ClassVar[frozenset[str]] = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"})

    def __init__(
        self,
        model: str,
        *,
        project: str | None = None,
        location: str = "global",
        temperature: float | None = 0.0,
        client: Any = None,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client
        self.model = model
        self.project = project
        self.location = location
        self.temperature = temperature
        self.label = f"vertex-gemini:{model}"

    def complete(
        self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int
    ) -> Completion:
        config: dict[str, Any] = {
            "system_instruction": system,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
            "max_output_tokens": max_tokens,
        }
        if self.temperature is not None:
            config["temperature"] = self.temperature
        r = self._client.models.generate_content(model=self.model, contents=user, config=config)

        meta = getattr(r, "usage_metadata", None)
        in_tokens = getattr(meta, "prompt_token_count", 0) or 0
        out_tokens = (getattr(meta, "candidates_token_count", 0) or 0) + (
            getattr(meta, "thoughts_token_count", 0) or 0
        )
        candidates = getattr(r, "candidates", None) or []
        if not candidates:
            block = getattr(getattr(r, "prompt_feedback", None), "block_reason", None)
            return Completion(None, in_tokens, out_tokens, "refused", str(block))
        reason = getattr(candidates[0].finish_reason, "name", str(candidates[0].finish_reason))
        finish: Finish = ("stop" if reason == "STOP" else "length" if reason == "MAX_TOKENS"
                          else "refused" if reason in self._REFUSED else "other")
        detail = None if finish in ("stop", "length") else reason
        return Completion(r.text, in_tokens, out_tokens, finish, detail)

    def describe(self) -> dict[str, Any]:
        return {"provider": "vertex-gemini", "model": self.model, "project": self.project,
                "location": self.location, "temperature": self.temperature}
