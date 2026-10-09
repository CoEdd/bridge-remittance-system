"""
The one place that talks to the Anthropic API (live mode only).

The model name comes from LLM_MODEL and the key from ANTHROPIC_API_KEY. Scripted mode
never imports this module's client, so the demo runs with no key and no internet.
"""

import json
from typing import Any

from app.config import get_settings

DEFAULT_MODEL = "claude-opus-5-5"

# Models that accept the server-side refusal fallback. On a safety refusal the API
# re-runs the same request on a fallback model inside the same call.
_FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LlmUnavailable(RuntimeError):
    """Claude could not be used for this request. Callers fall back to plain code."""


def model_name() -> str:
    return get_settings().llm_model or DEFAULT_MODEL


def get_client() -> Any:
    import anthropic

    key = get_settings().anthropic_api_key.get_secret_value()
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def complete_json(
    *, system: str, user: str, schema: dict[str, Any], client: Any = None, max_tokens: int = 4000
) -> dict[str, Any]:
    """
    One request that must answer with JSON matching `schema` (structured outputs).

    Raises LlmUnavailable on any API error, a refusal, or a truncated answer, so the
    caller can fall back to its deterministic path.
    """
    import anthropic

    client = client or get_client()
    model = model_name()
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    try:
        if model in _FALLBACK_MODELS:
            response = client.beta.messages.create(betas=[_FALLBACK_BETA], fallbacks="default", **request)
        else:
            response = client.messages.create(**request)
    except anthropic.APIError as error:
        raise LlmUnavailable(f"The Claude API call failed: {error}") from error

    if response.stop_reason in ("refusal", "max_tokens"):
        raise LlmUnavailable(f"Claude stopped early ({response.stop_reason}).")
    text = next((block.text for block in response.content if block.type == "text"), None)
    if text is None:
        raise LlmUnavailable("Claude returned no text.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise LlmUnavailable("Claude's answer was not valid JSON.") from error
    if not isinstance(parsed, dict):
        raise LlmUnavailable("Claude's answer was not a JSON object.")
    return parsed
