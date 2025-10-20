"""Retry utilities for GUARD."""

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from guard.utils.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_exception(
    exceptions: tuple[type[Exception], ...] = (Exception,),
    max_attempts: int = 3,
    min_wait: int = 1,
    max_wait: int = 10,
) -> Callable[[F], F]:
    """Decorator to retry a function on specific exceptions.

    Args:
        exceptions: Tuple of exception types to retry on
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        Decorated function with retry logic
    """

    def before_sleep(retry_state: RetryCallState) -> None:
        """Log before sleeping between retries."""
        if retry_state.outcome and retry_state.outcome.failed:
            exception = retry_state.outcome.exception()
            logger.warning(
                "retry_attempt",
                attempt=retry_state.attempt_number,
                max_attempts=max_attempts,
                exception=type(exception).__name__,
                message=str(exception),
            )

    return retry(
        retry=retry_if_exception_type(exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        before_sleep=before_sleep,
        reraise=True,
    )


def simple_retry(
    func: F,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> F:
    """Simple retry wrapper without using tenacity.

    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier
        exceptions: Exceptions to catch and retry

    Returns:
        Wrapped function
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        current_delay = delay
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                last_exception = e
                if attempt < max_attempts:
                    logger.warning(
                        "retry_attempt",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=current_delay,
                        exception=type(e).__name__,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

        # If we get here, all attempts failed
        logger.error(
            "retry_exhausted",
            max_attempts=max_attempts,
            exception=type(last_exception).__name__,
        )
        raise last_exception  # type: ignore

    return wrapper  # type: ignore
