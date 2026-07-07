"""
Brute force protection service.
Progressive rate limiting for failed authentication attempts.
Supports Requirement 13.6.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger(__name__)

# Progressive backoff thresholds
THRESHOLDS = [
    (3, 60),      # After 3 failures → block for 60s
    (5, 300),     # After 5 failures → block for 5min
    (10, 3600),   # After 10 failures → block for 1hr
]

MAX_TRACKED_IPS = 10000  # Prevent unbounded memory growth


@dataclass
class FailureRecord:
    """Tracks failed auth attempts for an IP/key."""
    count: int = 0
    first_failure: float = 0.0
    last_failure: float = 0.0
    blocked_until: float = 0.0


class BruteForceProtector:
    """
    Tracks failed authentication attempts and progressively
    rate-limits suspicious sources.

    In production, this would use Redis for distributed state.
    """

    def __init__(self):
        self._records: Dict[str, FailureRecord] = {}

    def record_failure(self, identifier: str) -> int:
        """
        Record a failed authentication attempt.

        Args:
            identifier: IP address or API key prefix.

        Returns:
            The block duration in seconds (0 if not blocked).
        """
        now = time.time()

        if identifier not in self._records:
            if len(self._records) >= MAX_TRACKED_IPS:
                # Evict oldest entries
                oldest = sorted(self._records, key=lambda k: self._records[k].last_failure)
                for key in oldest[:100]:
                    del self._records[key]

            self._records[identifier] = FailureRecord(first_failure=now)

        record = self._records[identifier]
        record.count += 1
        record.last_failure = now

        # Calculate block duration based on progressive thresholds
        block_duration = 0
        for threshold_count, duration in THRESHOLDS:
            if record.count >= threshold_count:
                block_duration = duration

        if block_duration > 0:
            record.blocked_until = now + block_duration
            logger.warning(
                "Brute force protection: %s blocked for %ds after %d failures",
                identifier, block_duration, record.count,
            )

        return block_duration

    def is_blocked(self, identifier: str) -> bool:
        """Check if an identifier is currently blocked."""
        record = self._records.get(identifier)
        if not record:
            return False
        return time.time() < record.blocked_until

    def get_block_remaining(self, identifier: str) -> int:
        """Get remaining block time in seconds."""
        record = self._records.get(identifier)
        if not record:
            return 0
        remaining = record.blocked_until - time.time()
        return max(0, int(remaining))

    def record_success(self, identifier: str):
        """Clear failure record on successful authentication."""
        self._records.pop(identifier, None)

    def get_failure_count(self, identifier: str) -> int:
        """Get current failure count for an identifier."""
        record = self._records.get(identifier)
        return record.count if record else 0

    def reset(self):
        """Clear all records."""
        self._records.clear()
