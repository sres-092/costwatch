"""Talks to the LLM. Knows nothing about budgets or users."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_UP

from . import config

MICRO = Decimal("0.000001")          # our NUMERIC(12,6) precision
ONE_MILLION = Decimal(1_000_000)


class LLMError(Exception):
    """The upstream LLM failed (timeout, bad key, outage, empty answer)."""


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal


def price(prompt_tokens: int, completion_tokens: int) -> Decimal:
    cost = (Decimal(prompt_tokens) * config.PRICE_INPUT_PER_M
            + Decimal(completion_tokens) * config.PRICE_OUTPUT_PER_M) / ONE_MILLION
    return cost.quantize(MICRO, rounding=ROUND_UP)   # always round in our favour


def max_cost(prompt: str) -> Decimal:
    """The MOST this call could possibly cost. We reserve this before calling."""
    if config.LLM_MODE == "mock":
        return config.MOCK_COST_USD
    # ~4 chars per token is typical; dividing by 3 over-estimates on purpose.
    estimated_prompt_tokens = len(prompt) // 3 + 1
    # max_output_tokens is a hard cap we send to Gemini, so output can't exceed it.
    return price(estimated_prompt_tokens, config.MAX_OUTPUT_TOKENS)


def model_name() -> str:
    return "mock" if config.LLM_MODE == "mock" else config.GEMINI_MODEL


def complete(prompt: str) -> LLMResult:
    if config.LLM_MODE == "mock":
        return _mock(prompt)
    return _gemini(prompt)


def _mock(prompt: str) -> LLMResult:
    text = f"[mock] You said: {prompt[:80]}"
    return LLMResult(
        text=text,
        model="mock",
        prompt_tokens=max(1, len(prompt) // 4),
        completion_tokens=max(1, len(text) // 4),
        cost=config.MOCK_COST_USD,
    )


_client = None


def _get_client():
    global _client
    if _client is None:   # create once, reuse for every request
        from google import genai
        from google.genai import types
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_SECONDS * 1000),
        )
    return _client


def _gemini(prompt: str) -> LLMResult:
    from google.genai import types
    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=config.MAX_OUTPUT_TOKENS),
        )
    except Exception as e:
                raise LLMError(f"Gemini call failed: {type(e).__name__}: {e}") from e

    usage = response.usage_metadata
    if usage is None:
        raise LLMError("Gemini returned no usage data")

    prompt_tokens = usage.prompt_token_count or 0
    # "thinking" tokens are billed as output, so count them too
    completion_tokens = (usage.candidates_token_count or 0) + (getattr(usage, "thoughts_token_count", 0) or 0)

    return LLMResult(
        text=response.text or "",
        model=config.GEMINI_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=price(prompt_tokens, completion_tokens),
    )