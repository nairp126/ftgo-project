"""
Tests for request logging system and PII redaction.
Covers log entry structure, PII masking, and property tests.
"""

import time
import uuid
from decimal import Decimal

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.services.request_logger import (
    RequestLogger,
    RequestLogEntry,
    REQUIRED_LOG_FIELDS,
)
from app.services.pii_redactor import (
    detect_pii,
    redact_pii,
    contains_pii,
    REDACTED,
)


# ===========================================================================
# PII Detection Unit Tests
# ===========================================================================


class TestPIIDetection:

    def test_detects_email(self):
        findings = detect_pii("Contact me at user@example.com please")
        assert any(f["type"] == "email" for f in findings)

    def test_detects_ssn(self):
        findings = detect_pii("My SSN is 123-45-6789")
        assert any(f["type"] == "ssn" for f in findings)

    def test_detects_phone(self):
        findings = detect_pii("Call me at (555) 123-4567")
        assert any(f["type"] == "phone" for f in findings)

    def test_detects_credit_card(self):
        findings = detect_pii("Card: 4111 1111 1111 1111")
        assert any(f["type"] == "credit_card" for f in findings)

    def test_no_pii_clean_text(self):
        findings = detect_pii("Hello, how are you today?")
        assert len(findings) == 0

    def test_multiple_pii(self):
        text = "Email user@test.com and SSN 111-22-3333"
        findings = detect_pii(text)
        types = {f["type"] for f in findings}
        assert "email" in types
        assert "ssn" in types


# ===========================================================================
# PII Redaction Unit Tests
# ===========================================================================


class TestPIIRedaction:

    def test_redacts_email(self):
        result = redact_pii("Contact user@example.com for info")
        assert "user@example.com" not in result
        assert REDACTED in result

    def test_redacts_ssn(self):
        result = redact_pii("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert REDACTED in result

    def test_redacts_phone(self):
        result = redact_pii("Phone: 555-123-4567")
        assert "555-123-4567" not in result
        assert REDACTED in result

    def test_preserves_clean_text(self):
        text = "Hello, this is a normal message"
        assert redact_pii(text) == text

    def test_redacts_multiple_pii(self):
        text = "Email: a@b.com, SSN: 111-22-3333"
        result = redact_pii(text)
        assert "a@b.com" not in result
        assert "111-22-3333" not in result
        assert result.count(REDACTED) >= 2

    def test_contains_pii_positive(self):
        assert contains_pii("user@test.com") is True

    def test_contains_pii_negative(self):
        assert contains_pii("no pii here") is False


# ===========================================================================
# Request Log Entry Unit Tests
# ===========================================================================


class TestRequestLogEntry:

    def test_auto_generates_uuid(self):
        entry = RequestLogEntry()
        assert entry.request_id is not None
        uuid.UUID(entry.request_id)  # Validates UUID format

    def test_auto_generates_timestamp(self):
        entry = RequestLogEntry()
        assert entry.timestamp is not None

    def test_to_dict_contains_all_fields(self):
        entry = RequestLogEntry(
            api_key_id="key-1",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=42.5,
            cost_usd=Decimal("0.001"),
            cache_status="MISS",
        )
        d = entry.to_dict()
        for field_name in REQUIRED_LOG_FIELDS:
            assert field_name in d, f"Missing field: {field_name}"

    def test_has_required_fields_true(self):
        entry = RequestLogEntry(
            api_key_id="key-1",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=42.5,
            cost_usd=Decimal("0.001"),
            cache_status="MISS",
            error_status=None,
        )
        assert entry.has_required_fields() is True

    def test_cost_serialised_as_string(self):
        entry = RequestLogEntry(cost_usd=Decimal("0.00125"))
        d = entry.to_dict()
        assert isinstance(d["cost_usd"], str)


# ===========================================================================
# Request Logger Unit Tests
# ===========================================================================


class TestRequestLogger:

    def test_log_stores_entry(self):
        logger = RequestLogger()
        entry = logger.create_entry(model="gpt-4o", provider="openai")
        logger.log(entry)
        assert len(logger.get_logs()) == 1

    def test_log_redacts_pii_in_error_message(self):
        rl = RequestLogger()
        entry = rl.create_entry(
            model="gpt-4o",
            error_message="Error for user@test.com with SSN 123-45-6789",
        )
        logged = rl.log(entry)
        assert "user@test.com" not in logged.error_message
        assert "123-45-6789" not in logged.error_message
        assert REDACTED in logged.error_message

    def test_get_log_by_id(self):
        rl = RequestLogger()
        entry = rl.create_entry(model="gpt-4o")
        rl.log(entry)
        found = rl.get_log_by_id(entry.request_id)
        assert found is not None
        assert found.request_id == entry.request_id

    def test_get_log_by_id_not_found(self):
        rl = RequestLogger()
        assert rl.get_log_by_id("nonexistent") is None

    def test_stats_empty(self):
        rl = RequestLogger()
        stats = rl.get_stats()
        assert stats["total"] == 0

    def test_stats_after_logging(self):
        rl = RequestLogger()
        rl.log(rl.create_entry(model="gpt-4o", cache_status="HIT"))
        rl.log(rl.create_entry(model="gpt-4o", cache_status="MISS"))
        rl.log(rl.create_entry(model="gpt-4o", error_status="provider_error"))

        stats = rl.get_stats()
        assert stats["total"] == 3
        assert stats["errors"] == 1
        assert stats["cache_hits"] == 1

    def test_clear_logs(self):
        rl = RequestLogger()
        rl.log(rl.create_entry(model="gpt-4o"))
        rl.clear()
        assert len(rl.get_logs()) == 0


# ===========================================================================
# Property Tests
# ===========================================================================


class TestLoggingCompletenessProperty:
    """Property 14: Request Logging Completeness (Requirements 6.1, 6.2)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        model=st.sampled_from(["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet-20241022"]),
        provider=st.sampled_from(["openai", "anthropic", "bedrock"]),
        prompt_tokens=st.integers(min_value=0, max_value=10000),
        completion_tokens=st.integers(min_value=0, max_value=10000),
        latency=st.floats(min_value=0.0, max_value=10000.0),
    )
    def test_log_entry_always_has_required_fields(
        self, model, provider, prompt_tokens, completion_tokens, latency
    ):
        """
        Property 14: Every log entry created by RequestLogger MUST
        contain all required fields (request_id, api_key_id, timestamp,
        model, provider, tokens, latency, cost, cache_status, error_status).
        """
        rl = RequestLogger()
        entry = rl.create_entry(
            api_key_id="test-key",
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency,
            cost_usd=Decimal("0.001"),
            cache_status="MISS",
        )
        logged = rl.log(entry)
        d = logged.to_dict()

        for field_name in REQUIRED_LOG_FIELDS:
            assert field_name in d, f"Missing required field: {field_name}"

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(st.data())
    def test_request_id_is_always_valid_uuid(self, data):
        """Property 14: request_id MUST always be a valid UUID."""
        entry = RequestLogEntry()
        parsed = uuid.UUID(entry.request_id)
        assert str(parsed) == entry.request_id


class TestPIIRedactionProperty:
    """Property 15: PII Redaction Consistency (Requirements 6.4, 13.4)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prefix=st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
        suffix=st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
    )
    def test_email_always_redacted(self, prefix, suffix):
        """Property 15: Emails MUST never survive redaction."""
        email = "test.user@example.com"
        text = f"{prefix} {email} {suffix}"
        result = redact_pii(text)
        assert email not in result

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prefix=st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
        suffix=st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
    )
    def test_ssn_always_redacted(self, prefix, suffix):
        """Property 15: SSNs MUST never survive redaction."""
        ssn = "123-45-6789"
        text = f"{prefix} {ssn} {suffix}"
        result = redact_pii(text)
        assert ssn not in result

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(text=st.text(min_size=0, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz .,!?"))
    def test_clean_text_unchanged(self, text):
        """Property 15: Text without PII MUST be returned unmodified."""
        result = redact_pii(text)
        assert result == text
