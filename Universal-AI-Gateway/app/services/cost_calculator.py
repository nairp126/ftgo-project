"""
Cost calculation service.
Calculates per-request costs based on provider pricing.
Supports Requirements 9.3, 9.5, 9.6.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (input / output) in USD
# Updated as of 2025-Q4 pricing
PROVIDER_PRICING: Dict[str, Dict[str, Dict[str, Decimal]]] = {
    "gpt-4o": {
        "input": Decimal("2.50"),
        "output": Decimal("10.00"),
    },
    "gpt-4o-mini": {
        "input": Decimal("0.15"),
        "output": Decimal("0.60"),
    },
    "gpt-4-turbo": {
        "input": Decimal("10.00"),
        "output": Decimal("30.00"),
    },
    "gpt-3.5-turbo": {
        "input": Decimal("0.50"),
        "output": Decimal("1.50"),
    },
    "claude-3-5-sonnet-20241022": {
        "input": Decimal("3.00"),
        "output": Decimal("15.00"),
    },
    "claude-3-5-haiku-20241022": {
        "input": Decimal("0.80"),
        "output": Decimal("4.00"),
    },
    "bedrock/claude-3-5-sonnet": {
        "input": Decimal("3.00"),
        "output": Decimal("15.00"),
    },
    "bedrock/claude-3-5-haiku": {
        "input": Decimal("0.80"),
        "output": Decimal("4.00"),
    },
    "bedrock/llama-3-70b": {
        "input": Decimal("0.99"),
        "output": Decimal("0.99"),
    },
    "bedrock/llama-3-8b": {
        "input": Decimal("0.22"),
        "output": Decimal("0.22"),
    },
    # Gemini models
    "gemini-1.5-pro": {
        "input": Decimal("1.25"),
        "output": Decimal("3.75"),
    },
    "gemini-1.5-flash": {
        "input": Decimal("0.075"),
        "output": Decimal("0.30"),
    },
    "gemini-1.0-pro": {
        "input": Decimal("0.50"),
        "output": Decimal("1.50"),
    },
}

ONE_MILLION = Decimal("1000000")


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """
    Calculate the cost for a request based on token counts.

    Args:
        model: Model name.
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Cost in USD as a Decimal, rounded to 8 decimal places.
    """
    pricing = PROVIDER_PRICING.get(model)
    if not pricing:
        logger.warning("No pricing data for model '%s'; cost will be 0", model)
        return Decimal("0")

    input_cost = (Decimal(prompt_tokens) / ONE_MILLION) * pricing["input"]
    output_cost = (Decimal(completion_tokens) / ONE_MILLION) * pricing["output"]
    total = (input_cost + output_cost).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    return total


def calculate_request_cost(
    model: str,
    token_usage: Dict[str, int],
) -> Dict[str, any]:
    """
    Calculate cost from a token usage dict.

    Args:
        model: Model name.
        token_usage: Dict with prompt_tokens, completion_tokens, total_tokens.

    Returns:
        Dict with cost_usd, model, and token breakdown.
    """
    prompt = token_usage.get("prompt_tokens", 0)
    completion = token_usage.get("completion_tokens", 0)
    cost = calculate_cost(model, prompt, completion)

    return {
        "model": model,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": token_usage.get("total_tokens", prompt + completion),
        "cost_usd": cost,
    }


def get_model_pricing(model: str) -> Optional[Dict[str, Decimal]]:
    """Get the pricing info for a model, or None if unknown."""
    return PROVIDER_PRICING.get(model)


def get_all_pricing() -> Dict[str, Dict[str, Decimal]]:
    """Return the full pricing table (useful for admin endpoints)."""
    return dict(PROVIDER_PRICING)
