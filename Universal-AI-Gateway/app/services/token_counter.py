"""
Token counting service using tiktoken.
Supports Requirements 9.1, 9.2, 9.4.
"""

import logging
from typing import List, Optional

import tiktoken

from app.schemas.chat import ChatRequest, ChatResponse, Message

logger = logging.getLogger(__name__)

# Model → tiktoken encoding mapping
MODEL_ENCODINGS = {
    # OpenAI models use cl100k_base or o200k_base
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    # Anthropic / Bedrock — tiktoken doesn't have native support,
    # so we use cl100k_base as a reasonable approximation
    "claude-3-5-sonnet-20241022": "cl100k_base",
    "claude-3-5-haiku-20241022": "cl100k_base",
    "bedrock/claude-3-5-sonnet": "cl100k_base",
    "bedrock/claude-3-5-haiku": "cl100k_base",
    "bedrock/llama-3-70b": "cl100k_base",
    "bedrock/llama-3-8b": "cl100k_base",
}

# Fallback encoding when model isn't in the map
DEFAULT_ENCODING = "cl100k_base"

# Per-message overhead tokens (OpenAI chat format)
TOKENS_PER_MESSAGE = 3  # <|start|>{role/name}\n
TOKENS_REPLY_OVERHEAD = 3  # assistant reply priming


def _get_encoding(model: str) -> tiktoken.Encoding:
    """Get the tiktoken encoding for a model."""
    enc_name = MODEL_ENCODINGS.get(model, DEFAULT_ENCODING)
    return tiktoken.get_encoding(enc_name)


def count_message_tokens(messages: List[Message], model: str) -> int:
    """
    Count the number of tokens in a list of chat messages.

    Uses tiktoken with per-message overhead matching OpenAI's counting logic.

    Args:
        messages: List of chat messages.
        model: Model name (determines encoding).

    Returns:
        Total token count for the prompt.
    """
    encoding = _get_encoding(model)
    total = 0

    for msg in messages:
        total += TOKENS_PER_MESSAGE
        total += len(encoding.encode(msg.role))
        total += len(encoding.encode(msg.content or ""))
        if msg.name:
            total += len(encoding.encode(msg.name))

    total += TOKENS_REPLY_OVERHEAD
    return total


def count_text_tokens(text: str, model: str) -> int:
    """
    Count tokens in a plain text string.

    Args:
        text: Raw text.
        model: Model name (determines encoding).

    Returns:
        Token count.
    """
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def count_request_tokens(request: ChatRequest) -> int:
    """Count input (prompt) tokens for a ChatRequest."""
    return count_message_tokens(request.messages, request.model)


def extract_response_tokens(response: ChatResponse) -> dict:
    """
    Extract token counts from a ChatResponse.

    Uses the provider-reported values when available, falls back
    to local counting.

    Returns:
        dict with prompt_tokens, completion_tokens, total_tokens
    """
    prompt = response.usage.prompt_tokens if response.usage else 0
    completion = response.usage.completion_tokens if response.usage else 0

    # If provider didn't report completion tokens, count locally
    if completion == 0 and response.choices:
        content = response.choices[0].message.content or ""
        completion = count_text_tokens(content, response.model)

    total = prompt + completion

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
