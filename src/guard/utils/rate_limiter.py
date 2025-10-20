"""Token-bucket rate limiter for API clients."""

import threading
import time
from functools import wraps
from typing import Callable, TypeVar

from guard.utils.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable)


class TokenBucket:
    """Thread-safe token bucket rate limiter.

    Implements the token bucket algorithm for rate limiting:
    - Bucket holds up to `capacity` tokens
    - Tokens refill at `refill_rate` tokens per second
    - Each operation consumes 1 token
    - If no tokens available, operation waits up to `max_wait` seconds
    """

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        max_wait: float = 60.0,
    ):
        """Initialize token bucket.

        Args:
            capacity: Maximum number of tokens in bucket
            refill_rate: Tokens added per second
            max_wait: Maximum time to wait for token (seconds)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.max_wait = max_wait

        self._tokens = float(capacity)
        self._lock = threading.Lock()
        self._last_refill = time.monotonic()

        logger.debug(
            "token_bucket_initialized",
            capacity=capacity,
            refill_rate=refill_rate,
            max_wait=max_wait,
        )

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill

        # Add tokens based on time elapsed
        tokens_to_add = elapsed * self.refill_rate
        self._tokens = min(self.capacity, self._tokens + tokens_to_add)
        self._last_refill = now

    def acquire(self, tokens: int = 1, wait: bool = True) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            wait: Whether to wait for tokens if unavailable

        Returns:
            True if tokens acquired, False if not available and wait=False

        Raises:
            TimeoutError: If waiting exceeds max_wait
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill()

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    logger.debug(
                        "tokens_acquired",
                        tokens=tokens,
                        remaining=self._tokens,
                    )
                    return True

            if not wait:
                logger.warning("tokens_unavailable", requested=tokens)
                return False

            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= self.max_wait:
                logger.error(
                    "token_acquisition_timeout",
                    elapsed=elapsed,
                    max_wait=self.max_wait,
                )
                raise TimeoutError(f"Rate limit: waited {elapsed:.1f}s for tokens")

            # Wait a bit before retrying
            time.sleep(0.1)

    def get_available_tokens(self) -> float:
        """Get current number of available tokens.

        Returns:
            Current token count
        """
        with self._lock:
            self._refill()
            return self._tokens


class RateLimiter:
    """Manager for multiple rate limiters by name."""

    def __init__(self):
        """Initialize rate limiter manager."""
        self._limiters: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

        logger.debug("rate_limiter_manager_initialized")

    def register(
        self,
        name: str,
        capacity: int,
        refill_rate: float,
        max_wait: float = 60.0,
    ) -> None:
        """Register a new rate limiter.

        Args:
            name: Unique identifier for this limiter
            capacity: Maximum tokens in bucket
            refill_rate: Tokens per second refill rate
            max_wait: Maximum wait time for tokens
        """
        with self._lock:
            if name in self._limiters:
                logger.warning("rate_limiter_already_registered", name=name)
                return

            self._limiters[name] = TokenBucket(
                capacity=capacity,
                refill_rate=refill_rate,
                max_wait=max_wait,
            )

            logger.info(
                "rate_limiter_registered",
                name=name,
                capacity=capacity,
                refill_rate=refill_rate,
            )

    def acquire(self, name: str, tokens: int = 1, wait: bool = True) -> bool:
        """Acquire tokens from named limiter.

        Args:
            name: Name of the rate limiter
            tokens: Number of tokens to acquire
            wait: Whether to wait for tokens

        Returns:
            True if tokens acquired, False otherwise

        Raises:
            ValueError: If limiter not registered
            TimeoutError: If wait exceeds max_wait
        """
        with self._lock:
            if name not in self._limiters:
                raise ValueError(f"Rate limiter '{name}' not registered")
            limiter = self._limiters[name]

        return limiter.acquire(tokens=tokens, wait=wait)

    def get_limiter(self, name: str) -> TokenBucket:
        """Get rate limiter by name.

        Args:
            name: Name of the rate limiter

        Returns:
            TokenBucket instance

        Raises:
            ValueError: If limiter not registered
        """
        with self._lock:
            if name not in self._limiters:
                raise ValueError(f"Rate limiter '{name}' not registered")
            return self._limiters[name]


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance.

    Returns:
        Global RateLimiter instance
    """
    return _rate_limiter


def rate_limited(limiter_name: str, tokens: int = 1) -> Callable[[F], F]:
    """Decorator to apply rate limiting to a function.

    Args:
        limiter_name: Name of the rate limiter to use
        tokens: Number of tokens to consume per call

    Returns:
        Decorated function

    Example:
        @rate_limited("gitlab_api")
        def create_merge_request(...):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            rate_limiter = get_rate_limiter()

            logger.debug(
                "rate_limit_checking",
                function=func.__name__,
                limiter=limiter_name,
                tokens=tokens,
            )

            # Acquire tokens before executing function
            rate_limiter.acquire(limiter_name, tokens=tokens, wait=True)

            # Execute the function
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
