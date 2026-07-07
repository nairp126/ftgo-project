"""
Tests for security hardening — brute force protection and security headers.
"""

import time

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.services.brute_force import BruteForceProtector, THRESHOLDS
from app.middleware.security import SECURITY_HEADERS


# ===========================================================================
# Brute Force Protection Tests
# ===========================================================================


class TestBruteForceProtector:

    def setup_method(self):
        self.bf = BruteForceProtector()

    def test_not_blocked_initially(self):
        assert self.bf.is_blocked("1.2.3.4") is False

    def test_blocked_after_threshold(self):
        for _ in range(3):
            self.bf.record_failure("1.2.3.4")
        assert self.bf.is_blocked("1.2.3.4") is True

    def test_failure_count_tracked(self):
        self.bf.record_failure("1.2.3.4")
        self.bf.record_failure("1.2.3.4")
        assert self.bf.get_failure_count("1.2.3.4") == 2

    def test_success_clears_record(self):
        self.bf.record_failure("1.2.3.4")
        self.bf.record_failure("1.2.3.4")
        self.bf.record_success("1.2.3.4")
        assert self.bf.get_failure_count("1.2.3.4") == 0
        assert self.bf.is_blocked("1.2.3.4") is False

    def test_progressive_blocking(self):
        """More failures = longer block duration."""
        bf = BruteForceProtector()
        # 3 failures → shortest block
        for _ in range(3):
            d = bf.record_failure("ip-a")
        block_3 = d

        bf2 = BruteForceProtector()
        # 10 failures → longest block
        for _ in range(10):
            d = bf2.record_failure("ip-b")
        block_10 = d

        assert block_10 > block_3

    def test_different_ips_independent(self):
        self.bf.record_failure("1.1.1.1")
        self.bf.record_failure("1.1.1.1")
        self.bf.record_failure("1.1.1.1")
        assert self.bf.is_blocked("1.1.1.1") is True
        assert self.bf.is_blocked("2.2.2.2") is False

    def test_get_block_remaining(self):
        for _ in range(3):
            self.bf.record_failure("1.2.3.4")
        remaining = self.bf.get_block_remaining("1.2.3.4")
        assert remaining > 0

    def test_reset_clears_all(self):
        self.bf.record_failure("1.2.3.4")
        self.bf.reset()
        assert self.bf.get_failure_count("1.2.3.4") == 0


# ===========================================================================
# Security Headers Tests
# ===========================================================================


class TestSecurityHeaders:

    def test_hsts_header_present(self):
        assert "Strict-Transport-Security" in SECURITY_HEADERS

    def test_content_type_options(self):
        assert SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"

    def test_frame_options_deny(self):
        assert SECURITY_HEADERS["X-Frame-Options"] == "DENY"

    def test_xss_protection(self):
        assert "X-XSS-Protection" in SECURITY_HEADERS

    def test_csp_present(self):
        assert "Content-Security-Policy" in SECURITY_HEADERS

    def test_referrer_policy(self):
        assert "Referrer-Policy" in SECURITY_HEADERS

    def test_all_required_headers_present(self):
        """Requirement 13.1: All security headers must be defined."""
        required = {
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Content-Security-Policy",
        }
        assert required.issubset(SECURITY_HEADERS.keys())


# ===========================================================================
# Property Tests
# ===========================================================================


class TestBruteForceProperty:
    """Property 22: Brute Force Protection (Requirement 13.6)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        ip=st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True),
        failures=st.integers(min_value=3, max_value=20),
    )
    def test_always_blocked_after_threshold(self, ip, failures):
        """
        Property 22: After >= 3 failures, the identifier MUST be blocked.
        """
        bf = BruteForceProtector()
        for _ in range(failures):
            bf.record_failure(ip)
        assert bf.is_blocked(ip) is True

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        ip=st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True),
    )
    def test_never_blocked_before_threshold(self, ip):
        """
        Property 22: Before reaching the threshold, the identifier MUST NOT be blocked.
        """
        bf = BruteForceProtector()
        bf.record_failure(ip)
        bf.record_failure(ip)
        assert bf.is_blocked(ip) is False
