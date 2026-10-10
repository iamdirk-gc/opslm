from types import SimpleNamespace as NS

import pytest

from opslm.baselines.backends import (
    AnthropicBackend,
    OpenAICompatibleBackend,
    VertexGeminiBackend,
)

SCHEMA = {"type": "object", "properties": {}}


# --- Anthropic -----------------------------------------------------------------


def anthropic_client(stop="end_turn", text='{"a": 1}', usage=(10, 5)):
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(
            content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
            stop_reason=stop,
            stop_details=NS(category="cyber") if stop == "refusal" else None,
            usage=NS(input_tokens=usage[0], output_tokens=usage[1]),
        )

    return NS(messages=NS(create=create)), calls


def test_anthropic_request_shape_and_result():
    client, calls = anthropic_client()
    b = AnthropicBackend("claude-opus-5-5", effort="high", client=client)
    c = b.complete("sys", "user", SCHEMA, max_tokens=99)
    call = calls[0]
    assert call["output_config"]["effort"] == "high"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "betas", "fallbacks", "thinking"):
        assert forbidden not in call
    assert (c.text, c.input_tokens, c.output_tokens, c.finish) == ('{"a": 1}', 10, 5, "stop")
    assert b.label == "anthropic:claude-opus-5-5:high"
    assert b.describe()["server_side_fallbacks"] is False


@pytest.mark.parametrize(
    "stop,finish,detail",
    [("refusal", "refused", "cyber"), ("max_tokens", "length", None), ("pause_turn", "other", "pause_turn")],
)
def test_anthropic_stop_reasons(stop, finish, detail):
    client, _ = anthropic_client(stop=stop)
    c = AnthropicBackend("m", client=client).complete("s", "u", SCHEMA, max_tokens=1)
    assert (c.finish, c.detail) == (finish, detail)


# --- OpenAI-compatible ---------------------------------------------------------


def openai_client(finish="stop", content='{"a": 1}', usage=(7, 3)):
    calls = []

    def create(**kw):
        calls.append(kw)
        return NS(
            choices=[NS(finish_reason=finish, message=NS(content=content))],
            usage=NS(prompt_tokens=usage[0], completion_tokens=usage[1]),
        )

    return NS(chat=NS(completions=NS(create=create))), calls


def test_openai_json_schema_mode():
    client, calls = openai_client()
    b = OpenAICompatibleBackend("qwen", client=client, base_url="http://localhost:8000/v1")
    c = b.complete("sys", "user", SCHEMA, max_tokens=50)
    call = calls[0]
    assert call["response_format"]["json_schema"]["schema"] == SCHEMA
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["temperature"] == 0.0 and call["max_tokens"] == 50
    assert call["messages"][0] == {"role": "system", "content": "sys"}
    assert (c.input_tokens, c.output_tokens, c.finish) == (7, 3, "stop")
    assert b.describe()["base_url"] == "http://localhost:8000/v1"


@pytest.mark.parametrize("mode,has_format", [("json_object", True), ("none", False)])
def test_openai_weaker_modes_put_schema_in_prompt(mode, has_format):
    client, calls = openai_client()
    OpenAICompatibleBackend("m", client=client, structured=mode).complete(
        "sys", "u", SCHEMA, max_tokens=5
    )
    call = calls[0]
    assert ("response_format" in call) is has_format
    assert "JSON schema" in call["messages"][0]["content"]


def test_openai_max_completion_tokens_and_no_temperature():
    client, calls = openai_client()
    b = OpenAICompatibleBackend("m", client=client, max_tokens_param="max_completion_tokens",
                                temperature=None)
    b.complete("s", "u", SCHEMA, max_tokens=5)
    assert calls[0]["max_completion_tokens"] == 5 and "temperature" not in calls[0]
    assert "max_tokens" not in calls[0]


@pytest.mark.parametrize(
    "reason,finish", [("length", "length"), ("content_filter", "refused"), ("tool_calls", "other")]
)
def test_openai_finish_reasons(reason, finish):
    client, _ = openai_client(finish=reason)
    c = OpenAICompatibleBackend("m", client=client).complete("s", "u", SCHEMA, max_tokens=1)
    assert c.finish == finish


def test_openai_missing_usage_is_zero():
    client, _ = openai_client()
    client.chat.completions.create = lambda **kw: NS(
        choices=[NS(finish_reason="stop", message=NS(content="x"))], usage=None
    )
    c = OpenAICompatibleBackend("m", client=client).complete("s", "u", SCHEMA, max_tokens=1)
    assert (c.input_tokens, c.output_tokens) == (0, 0)


# --- Vertex Gemini -------------------------------------------------------------


def gemini_client(finish="STOP", text='{"a": 1}', candidates=True, usage=(20, 6, 4)):
    calls = []

    def generate_content(**kw):
        calls.append(kw)
        return NS(
            text=text,
            candidates=[NS(finish_reason=NS(name=finish))] if candidates else [],
            prompt_feedback=NS(block_reason="PROHIBITED_CONTENT"),
            usage_metadata=NS(prompt_token_count=usage[0], candidates_token_count=usage[1],
                              thoughts_token_count=usage[2]),
        )

    return NS(models=NS(generate_content=generate_content)), calls


def test_gemini_request_shape_and_thinking_tokens_billed_as_output():
    client, calls = gemini_client()
    b = VertexGeminiBackend("gemini-x", project="p", client=client)
    c = b.complete("sys", "user", SCHEMA, max_tokens=77)
    cfg = calls[0]["config"]
    assert calls[0]["model"] == "gemini-x" and calls[0]["contents"] == "user"
    assert cfg["system_instruction"] == "sys" and cfg["response_json_schema"] == SCHEMA
    assert cfg["response_mime_type"] == "application/json" and cfg["max_output_tokens"] == 77
    assert (c.input_tokens, c.output_tokens, c.finish) == (20, 10, "stop")
    assert b.describe()["project"] == "p"


@pytest.mark.parametrize(
    "reason,finish",
    [("MAX_TOKENS", "length"), ("SAFETY", "refused"), ("OTHER", "other")],
)
def test_gemini_finish_reasons(reason, finish):
    client, _ = gemini_client(finish=reason)
    assert VertexGeminiBackend("m", client=client).complete("s", "u", SCHEMA, max_tokens=1).finish == finish


def test_gemini_prompt_block_is_refusal():
    client, _ = gemini_client(candidates=False)
    c = VertexGeminiBackend("m", client=client).complete("s", "u", SCHEMA, max_tokens=1)
    assert c.finish == "refused" and "PROHIBITED_CONTENT" in c.detail
