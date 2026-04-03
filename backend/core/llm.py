"""
Unified LLM dispatcher.

Routes structured tool-call requests to either the Anthropic API or a
local Ollama instance, based on the backend configured for each agent in
config.yaml.

Usage:
    from backend.core.llm import call_structured_llm

    result = await call_structured_llm(
        agent_name="fundamental",
        prompt="...",
        tool_description="Submit the fundamental signal",
        schema=FundamentalSignal.model_json_schema(),
        max_tokens=1024,
    )
    # result is a plain dict matching the schema
"""

from __future__ import annotations

import asyncio
import json

import httpx
import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.model_router import get_model_router

# Ollama runs one inference at a time; serialise requests so the httpx
# timeout only starts when inference actually begins, not while queuing.
_ollama_sem = asyncio.Semaphore(1)

log = structlog.get_logger()

_anthropic_client: AsyncAnthropic | None = None


def _get_anthropic_client() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic()
    return _anthropic_client


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def call_structured_llm(
    agent_name: str,
    prompt: str,
    tool_description: str,
    schema: dict,
    max_tokens: int = 1024,
) -> dict:
    """
    Call the LLM configured for *agent_name* with a single structured
    tool-call request. Returns the tool input as a plain dict.

    Dispatches to Anthropic or Ollama based on config.yaml.
    Retries up to 4 times with exponential back-off on any failure.
    """
    router = get_model_router()
    backend = router.get_backend(agent_name)
    model = router.get_model(agent_name)

    clean_schema = {k: v for k, v in schema.items() if k not in ("$defs", "title")}

    log.debug("llm_dispatch", agent=agent_name, backend=backend, model=model)

    if backend == "ollama":
        return await _call_ollama(
            model, prompt, tool_description, clean_schema, max_tokens,
            base_url=router.get_ollama_base_url(),
        )
    return await _call_anthropic(model, prompt, tool_description, clean_schema, max_tokens)


async def _call_anthropic(
    model: str,
    prompt: str,
    tool_description: str,
    schema: dict,
    max_tokens: int,
) -> dict:
    client = _get_anthropic_client()
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[{"name": "submit", "description": tool_description, "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise ValueError(f"No tool_use block in Anthropic response (model={model})")


async def _call_ollama(
    model: str,
    prompt: str,
    tool_description: str,
    schema: dict,
    max_tokens: int,
    base_url: str,
) -> dict:
    """Call Ollama's OpenAI-compatible /v1/chat/completions endpoint with tool calling.

    Serialises requests via _ollama_sem so that the httpx timeout only starts
    when inference actually begins — not while waiting in Ollama's queue.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "submit",
                "description": tool_description,
                "parameters": schema,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": "submit"}},
        "max_tokens": max_tokens,
        "stream": False,
    }
    # Serialise Ollama requests — only one runs at a time so the timeout
    # starts when inference begins, not while waiting in Ollama's queue.
    # Allow up to 10 minutes per request for large local models.
    async with _ollama_sem:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(f"{base_url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        raise ValueError("Empty choices in Ollama response")

    tool_calls = choices[0].get("message", {}).get("tool_calls", [])
    if not tool_calls:
        raise ValueError("No tool_calls in Ollama response — model may not support tool calling")

    arguments = tool_calls[0]["function"]["arguments"]
    # Ollama returns arguments as a JSON string; parse it
    if isinstance(arguments, str):
        return json.loads(arguments)
    return dict(arguments)
