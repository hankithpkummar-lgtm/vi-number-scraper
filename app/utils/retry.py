"""
Retry engine with exponential backoff, jitter, and circuit breaker.
"""

import asyncio
import functools
import logging
import random
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    async def record_success(self) -> None:
        """Record a successful call."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    async def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self._failure_count} failures"
            )

    async def can_execute(self) -> bool:
        """Check if a call is allowed."""
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0


def retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    multiplier: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Decorator for retrying failed function calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        multiplier: Multiplier for exponential backoff
        jitter: Whether to add random jitter
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (multiplier ** attempt), max_delay)
                    if jitter:
                        delay += random.uniform(0, 1)
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}. "
                        f"Waiting {delay:.2f}s"
                    )
                    time.sleep(delay)
            raise RetryExhaustedError(
                f"All {max_retries} retries exhausted for {func.__name__}: {last_exception}"
            )
        return wrapper
    return decorator


def async_retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    multiplier: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Decorator for retrying failed async function calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        multiplier: Multiplier for exponential backoff
        jitter: Whether to add random jitter
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (multiplier ** attempt), max_delay)
                    if jitter:
                        delay += random.uniform(0, 1)
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}. "
                        f"Waiting {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
            raise RetryExhaustedError(
                f"All {max_retries} retries exhausted for {func.__name__}: {last_exception}"
            )
        return wrapper
    return decorator


class HealthCheck:
    """Health check integration for monitoring service health."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable] = {}
        self._last_results: dict[str, dict] = {}

    def register(self, name: str, check_func: Callable) -> None:
        """Register a health check function."""
        self._checks[name] = check_func

    async def run_checks(self) -> dict[str, dict]:
        """Run all registered health checks."""
        results = {}
        for name, check_func in self._checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                results[name] = {"status": "healthy", "details": result}
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
        self._last_results = results
        return results

    def get_last_results(self) -> dict[str, dict]:
        """Get the last health check results."""
        return self._last_results
