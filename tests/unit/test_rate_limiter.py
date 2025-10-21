"""Unit tests for rate limiter."""

import time
from threading import Thread

import pytest

from guard.utils.rate_limiter import (
    RateLimiter,
    TokenBucket,
    get_rate_limiter,
    rate_limited,
)

# Mark all tests in this module to skip rate limiter mocking
pytestmark = pytest.mark.no_rate_limiter_mock


class TestTokenBucket:
    """Test TokenBucket class."""

    def test_token_bucket_initialization(self):
        """Test token bucket initializes correctly."""
        bucket = TokenBucket(capacity=100, refill_rate=10.0, max_wait=60.0)

        assert bucket.capacity == 100
        assert bucket.refill_rate == 10.0
        assert bucket.max_wait == 60.0
        assert bucket.get_available_tokens() == 100

    def test_token_acquisition_success(self):
        """Test successful token acquisition."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        # Should succeed
        assert bucket.acquire(tokens=5, wait=False) is True
        assert bucket.get_available_tokens() < 10

    def test_token_acquisition_insufficient(self):
        """Test token acquisition fails when insufficient tokens."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)

        # Acquire all tokens
        assert bucket.acquire(tokens=5, wait=False) is True

        # Should fail without waiting
        assert bucket.acquire(tokens=1, wait=False) is False

    def test_token_refill(self):
        """Test tokens refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        # Consume all tokens
        bucket.acquire(tokens=10, wait=False)
        assert bucket.get_available_tokens() < 1

        # Wait for refill (1 second = 10 tokens)
        time.sleep(1.1)

        # Should have refilled
        assert bucket.get_available_tokens() >= 9

    def test_token_acquisition_timeout(self):
        """Test token acquisition times out."""
        bucket = TokenBucket(capacity=1, refill_rate=0.1, max_wait=0.5)

        # Consume token
        bucket.acquire(tokens=1, wait=False)

        # Should timeout waiting for tokens
        with pytest.raises(TimeoutError):
            bucket.acquire(tokens=1, wait=True)

    def test_concurrent_token_acquisition(self):
        """Test thread-safe token acquisition."""
        bucket = TokenBucket(capacity=100, refill_rate=100.0)
        results = []

        def acquire_tokens():
            result = bucket.acquire(tokens=10, wait=False)
            results.append(result)

        threads = [Thread(target=acquire_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All acquisitions should succeed
        assert sum(results) == 10


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_rate_limiter_registration(self):
        """Test registering rate limiters."""
        limiter = RateLimiter()

        limiter.register(name="test_api", capacity=100, refill_rate=10.0)

        # Should not raise
        limiter.get_limiter("test_api")

    def test_rate_limiter_duplicate_registration(self):
        """Test duplicate registration is handled."""
        limiter = RateLimiter()

        limiter.register(name="test_api", capacity=100, refill_rate=10.0)
        limiter.register(name="test_api", capacity=200, refill_rate=20.0)

        # Should still have original limiter
        bucket = limiter.get_limiter("test_api")
        assert bucket.capacity == 100

    def test_rate_limiter_acquire(self):
        """Test acquiring tokens from named limiter."""
        limiter = RateLimiter()
        limiter.register(name="test_api", capacity=10, refill_rate=10.0)

        assert limiter.acquire("test_api", tokens=5, wait=False) is True

    def test_rate_limiter_unknown_limiter(self):
        """Test acquiring from unknown limiter raises error."""
        limiter = RateLimiter()

        with pytest.raises(ValueError, match="not registered"):
            limiter.acquire("unknown_api", tokens=1)


class TestRateLimitedDecorator:
    """Test rate_limited decorator."""

    def test_rate_limited_decorator_basic(self):
        """Test basic rate limiting with decorator."""
        # Register a test limiter
        limiter = get_rate_limiter()
        limiter.register(name="test_decorator", capacity=2, refill_rate=1.0)

        call_count = 0

        @rate_limited("test_decorator")
        def test_function():
            nonlocal call_count
            call_count += 1
            return "success"

        # First two calls should succeed
        assert test_function() == "success"
        assert test_function() == "success"
        assert call_count == 2

        # Third call should block/timeout
        # (We'll test with wait=False behavior in the bucket tests)

    def test_rate_limited_preserves_function_metadata(self):
        """Test decorator preserves function metadata."""
        limiter = get_rate_limiter()
        limiter.register(name="test_metadata", capacity=10, refill_rate=10.0)

        @rate_limited("test_metadata")
        def documented_function():
            """This is documentation."""
            pass

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is documentation."


class TestRateLimiterIntegration:
    """Integration tests for rate limiter."""

    def test_rate_limiting_prevents_burst(self):
        """Test rate limiter prevents burst traffic."""
        limiter = RateLimiter()
        limiter.register(name="burst_test", capacity=5, refill_rate=1.0)

        # Acquire 5 tokens quickly
        for _ in range(5):
            assert limiter.acquire("burst_test", tokens=1, wait=False) is True

        # Next acquisition should fail (no tokens left)
        assert limiter.acquire("burst_test", tokens=1, wait=False) is False

    def test_rate_limiting_refill_allows_more_requests(self):
        """Test tokens refill and allow more requests."""
        limiter = RateLimiter()
        limiter.register(name="refill_test", capacity=5, refill_rate=5.0)

        # Consume all tokens
        for _ in range(5):
            limiter.acquire("refill_test", tokens=1, wait=False)

        # Wait for refill
        time.sleep(1.1)

        # Should be able to acquire again
        assert limiter.acquire("refill_test", tokens=1, wait=False) is True
