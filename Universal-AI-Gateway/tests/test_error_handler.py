"""
Tests for the standardized error handling system.
Covers error builders, response structure, and property tests.
"""

import uuid

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.services.error_handler import (
    ErrorResponse,
    ErrorDetail,
    build_error_response,
    generate_correlation_id,
    get_status_code,
    authentication_error,
    authorization_error,
    rate_limit_error,
    provider_error,
    validation_error,
    internal_error,
    ERROR_TYPES,
)


# ===========================================================================
# Correlation ID Tests
# ===========================================================================


class TestCorrelationID:

    def test_generates_valid_uuid(self):
        cid = generate_correlation_id()
        uuid.UUID(cid)  # Validates format

    def test_generates_unique_ids(self):
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100


# ===========================================================================
# Error Response Builder Tests
# ===========================================================================


class TestBuildErrorResponse:

    def test_basic_structure(self):
        resp = build_error_response("internal_error", "Something broke")
        assert resp.error.type == "internal_error"
        assert resp.error.message == "Something broke"
        assert resp.error.correlation_id is not None

    def test_custom_correlation_id(self):
        resp = build_error_response("internal_error", "msg", correlation_id="custom-123")
        assert resp.error.correlation_id == "custom-123"

    def test_retry_after(self):
        resp = build_error_response("rate_limit_exceeded", "slow down", retry_after=30)
        assert resp.error.retry_after == 30

    def test_serializes_to_dict(self):
        resp = build_error_response("validation_error", "bad input")
        d = resp.model_dump()
        assert "error" in d
        assert "type" in d["error"]
        assert "message" in d["error"]
        assert "correlation_id" in d["error"]

    def test_serializes_to_json(self):
        resp = build_error_response("internal_error", "oops")
        json_str = resp.model_dump_json()
        assert "internal_error" in json_str
        assert "oops" in json_str


# ===========================================================================
# Status Code Mapping Tests
# ===========================================================================


class TestStatusCodeMapping:

    def test_authentication_401(self):
        assert get_status_code("authentication_error") == 401

    def test_authorization_403(self):
        assert get_status_code("authorization_error") == 403

    def test_rate_limit_429(self):
        assert get_status_code("rate_limit_exceeded") == 429

    def test_provider_error_502(self):
        assert get_status_code("provider_error") == 502

    def test_provider_unavailable_503(self):
        assert get_status_code("provider_unavailable") == 503

    def test_validation_400(self):
        assert get_status_code("validation_error") == 400

    def test_internal_500(self):
        assert get_status_code("internal_error") == 500

    def test_unknown_defaults_to_500(self):
        assert get_status_code("unknown_type") == 500


# ===========================================================================
# Convenience Builder Tests
# ===========================================================================


class TestConvenienceBuilders:

    def test_authentication_error(self):
        resp, code = authentication_error()
        assert code == 401
        assert resp.error.type == "authentication_error"

    def test_authorization_error(self):
        resp, code = authorization_error()
        assert code == 403
        assert resp.error.type == "authorization_error"

    def test_rate_limit_error(self):
        resp, code = rate_limit_error(retry_after=30)
        assert code == 429
        assert resp.error.retry_after == 30

    def test_provider_error_502(self):
        resp, code = provider_error(status_code=502)
        assert code == 502
        assert resp.error.type == "provider_error"

    def test_provider_error_503(self):
        resp, code = provider_error(status_code=503)
        assert code == 503
        assert resp.error.type == "provider_unavailable"

    def test_validation_error(self):
        resp, code = validation_error()
        assert code == 400
        assert resp.error.type == "validation_error"

    def test_internal_error(self):
        resp, code = internal_error()
        assert code == 500
        assert resp.error.type == "internal_error"

    def test_custom_message(self):
        resp, _ = authentication_error(message="Token expired")
        assert resp.error.message == "Token expired"

    def test_custom_correlation_id(self):
        resp, _ = internal_error(correlation_id="abc-123")
        assert resp.error.correlation_id == "abc-123"


# ===========================================================================
# Property Tests — Error Response Standardization (Property 7)
# ===========================================================================


REQUIRED_FIELDS = {"type", "message", "correlation_id"}


class TestErrorResponseStandardizationProperty:
    """Property 7: Error Response Standardization (Requirements 8.1–8.7)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        error_type=st.sampled_from(list(ERROR_TYPES.keys())),
        message=st.text(min_size=1, max_size=200),
    )
    def test_all_error_types_produce_standard_structure(self, error_type, message):
        """
        Property 7: Every error response MUST contain type, message,
        and correlation_id regardless of error category.
        """
        resp = build_error_response(error_type, message)
        d = resp.model_dump()

        assert "error" in d
        for field in REQUIRED_FIELDS:
            assert field in d["error"], f"Missing field: {field}"

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(error_type=st.sampled_from(list(ERROR_TYPES.keys())))
    def test_correlation_id_is_always_valid_uuid(self, error_type):
        """Property 7: correlation_id MUST always be a valid UUID."""
        resp = build_error_response(error_type, "test")
        uuid.UUID(resp.error.correlation_id)

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(error_type=st.sampled_from(list(ERROR_TYPES.keys())))
    def test_status_code_always_maps(self, error_type):
        """Property 7: Every error type MUST map to a valid HTTP status code."""
        code = get_status_code(error_type)
        assert 400 <= code <= 599
