"""
Retry mechanism with exponential backoff for provider requests.
Supports Requirement 3.6: retry with exponential backoff up to 3 attempts.
"""

import asyncio
import random
from typing import TypeVar, Callable, Awaitable, Optional, Type, Tuple

from app.core.logging import get_logger
from app.providers.base import ProviderError, ProviderRateLimitError

logger = get_logger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (ProviderError,),
    non_retryable_exceptions: Tuple[Type[Exception], ...] = (),
    **kwargs,
) -> T:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: The async function to execute.
        *args: Positional arguments for the function.
        max_retries: Maximum number of retry attempts (3 per Requirement 3.6).
        base_delay: Initial delay in seconds between retries.
        max_delay: Maximum delay cap in seconds.
        jitter: If True, add random jitter to prevent thundering herd.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        non_retryable_exceptions: Exceptions that should NOT be retried even if
            they're subclasses of retryable_exceptions.
        **kwargs: Keyword arguments for the function.

    Returns:
        The result of the function call.

    Raises:
        The last exception encountered if all retries are exhausted.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except non_retryable_exceptions:
            raise  # Don't retry auth errors, etc.
        except retryable_exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"All {max_retries} retries exhausted",
                    attempt=attempt,
                    error=str(e),
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

            # Handle rate limit with Retry-After
            if isinstance(e, ProviderRateLimitError) and e.retry_after:
                delay = max(delay, float(e.retry_after))

            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random())

            logger.warning(
                f"Retry {attempt}/{max_retries} after {delay:.2f}s",
                attempt=attempt,
                delay=delay,
                error=str(e),
            )

            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic completed without result or exception")
