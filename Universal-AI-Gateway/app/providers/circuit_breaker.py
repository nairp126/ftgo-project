"""
Circuit breaker pattern for provider health management.
Supports Requirements 3.7 (circuit breaker for health checking).

States:
  CLOSED   → Normal operation, requests pass through
  OPEN     → Provider is unhealthy, requests are immediately rejected
  HALF_OPEN → Testing if provider has recovered
"""

import time
from enum import Enum
from typing import Optional

from app.core.logging import get_logger
from app.services.notifier import get_notifier

logger = get_logger(__name__)


from app.cache.redis import redis_manager


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Distributed Redis-backed circuit breaker for protecting against cascading provider failures.

    Configuration:
        failure_threshold: Number of consecutive failures before opening circuit
        recovery_timeout:  Seconds to wait before trying half-open
        success_threshold: Consecutive successes needed to close from half-open
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        # Setup Redis keys
        self._key_state = f"cb:{self.name}:state"
        self._key_failures = f"cb:{self.name}:failures"
        self._key_successes = f"cb:{self.name}:successes"
        self._key_last_failure = f"cb:{self.name}:last_failure"

    async def _get_state(self) -> CircuitState:
        """Fetch current state from Redis, defaulting to CLOSED."""
        client = redis_manager.get_client()
        state_bytes = await client.get(self._key_state)
        # Assuming decode_responses=True on pool, but just in case:
        state_str = state_bytes if isinstance(state_bytes, str) else (state_bytes.decode('utf-8') if state_bytes else None)
        if not state_str:
            return CircuitState.CLOSED
        try:
            return CircuitState(state_str)
        except ValueError:
            return CircuitState.CLOSED

    async def get_state(self) -> CircuitState:
        """Get current circuit state, auto-transitioning OPEN → HALF_OPEN if recovery timeout has elapsed."""
        current_state = await self._get_state()
        if current_state == CircuitState.OPEN:
            client = redis_manager.get_client()
            last_failure_str = await client.get(self._key_last_failure)
            if last_failure_str:
                last_failure_time = float(last_failure_str)
                if time.time() - last_failure_time >= self.recovery_timeout:
                    await self._transition(CircuitState.HALF_OPEN)
                    return CircuitState.HALF_OPEN
        return current_state

    async def is_available(self) -> bool:
        """Whether requests are allowed through this circuit."""
        return await self.get_state() != CircuitState.OPEN

    async def record_success(self) -> None:
        """Record a successful request."""
        client = redis_manager.get_client()
        await client.set(self._key_failures, 0)

        current_state = await self._get_state()
        if current_state == CircuitState.HALF_OPEN:
            success_count = await client.incr(self._key_successes)
            if success_count >= self.success_threshold:
                await self._transition(CircuitState.CLOSED)
                logger.info("Circuit '%s' recovered → CLOSED", self.name)
        elif current_state != CircuitState.CLOSED:
            await self._transition(CircuitState.CLOSED)

    async def record_failure(self) -> None:
        """Record a failed request."""
        client = redis_manager.get_client()
        failures = await client.incr(self._key_failures)
        await client.set(self._key_successes, 0)
        await client.set(self._key_last_failure, time.time())

        current_state = await self._get_state()
        if current_state == CircuitState.HALF_OPEN:
            # Any failure in half-open immediately reopens
            await self._transition(CircuitState.OPEN)
            logger.warning("Circuit '%s' failed in HALF_OPEN → OPEN", self.name)
        elif (
            current_state == CircuitState.CLOSED
            and failures >= self.failure_threshold
        ):
            await self._transition(CircuitState.OPEN)
            logger.warning(
                "Circuit '%s' opened after %d failures", self.name, failures
            )

    async def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        await self._transition(CircuitState.CLOSED)
        client = redis_manager.get_client()
        await client.set(self._key_failures, 0)
        await client.set(self._key_successes, 0)
        await client.delete(self._key_last_failure)

    async def _transition(self, new_state: CircuitState) -> None:
        client = redis_manager.get_client()
        await client.set(self._key_state, new_state.value)
        
        # Alert on state transition
        await get_notifier().notify(
            "CIRCUIT_STATE_CHANGE",
            f"Provider circuit '{self.name}' transitioned to {new_state.value.upper()}",
            {"provider": self.name, "state": new_state.value}
        )

        if new_state == CircuitState.CLOSED:
            await client.set(self._key_failures, 0)
            await client.set(self._key_successes, 0)

    async def get_status(self) -> dict:
        """Get circuit breaker status for health reporting."""
        client = redis_manager.get_client()
        state = await self.get_state()
        failures = await client.get(self._key_failures)
        failures = int(failures) if failures else 0
        return {
            "name": self.name,
            "state": state.value,
            "failure_count": failures,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }
