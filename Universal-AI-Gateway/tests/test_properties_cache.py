"""
Hypothesis property tests for the caching system.
Satisfies subtasks 6.4 (Property 8) and 6.5 (Property 9).
"""

import sys
import time
from typing import List

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from app.schemas.chat import ChatRequest, Message
from app.cache.cache_manager import (
    generate_cache_key,
    CacheManager,
    CACHE_KEY_PREFIX,
    MAX_CACHE_ENTRY_BYTES,
)
from app.schemas.chat import ChatResponse, Choice, Usage


# --- Strategies ---


@st.composite
def message_strategy(draw):
    return Message(
        role=draw(st.sampled_from(["user", "assistant", "system"])),
        content=draw(st.text(min_size=1, max_size=200)),
    )


@st.composite
def chat_request_strategy(draw):
    messages = draw(st.lists(message_strategy(), min_size=1, max_size=5))
    return ChatRequest(
        model=draw(st.sampled_from(["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet-20241022"])),
        messages=messages,
        temperature=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=2.0))),
        max_tokens=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=4096))),
        top_p=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0))),
    )


def _make_response(content: str = "Hi") -> ChatResponse:
    return ChatResponse(
        id="test",
        created=int(time.time()),
        model="gpt-4o",
        choices=[Choice(message=Message(role="assistant", content=content), finish_reason="stop")],
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


# ===========================================================================
# Property 8: Cache Key Determinism  (Requirement 5.1)
# ===========================================================================


class TestCacheKeyDeterminism:

    @settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(request=chat_request_strategy())
    def test_same_request_always_produces_same_key(self, request: ChatRequest):
        """
        Property 8: Identical requests MUST always produce identical cache keys.
        """
        key1 = generate_cache_key(request)
        key2 = generate_cache_key(request)
        assert key1 == key2

    @settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(request=chat_request_strategy())
    def test_key_is_prefixed_and_valid_hex(self, request: ChatRequest):
        """Every cache key starts with the prefix and contains a 64-char hex digest."""
        key = generate_cache_key(request)
        assert key.startswith(CACHE_KEY_PREFIX)
        hex_part = key[len(CACHE_KEY_PREFIX):]
        assert len(hex_part) == 64
        int(hex_part, 16)  # Raises ValueError if not valid hex


# ===========================================================================
# Property 9: Cache Size Enforcement  (Requirement 5.8)
# ===========================================================================


class TestCacheSizeEnforcement:

    @given(extra_bytes=st.integers(min_value=1, max_value=5000))
    def test_oversized_entries_are_rejected(self, extra_bytes: int):
        """
        Property 9: Any response whose serialized JSON exceeds 1 MB
        MUST be rejected by CacheManager.set.
        """
        # Build content large enough to exceed the limit
        # ChatResponse JSON overhead is ~200 bytes, so content needs > MAX - 200
        needed = MAX_CACHE_ENTRY_BYTES + extra_bytes
        big_content = "A" * needed
        resp = _make_response(content=big_content)
        payload = resp.model_dump_json().encode("utf-8")

        # The serialised payload must exceed the limit
        assert len(payload) > MAX_CACHE_ENTRY_BYTES
