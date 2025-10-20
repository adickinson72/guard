"""Tests for retry utilities."""

import pytest

from guard.core.exceptions import GuardError
from guard.utils.retry import retry_on_exception, simple_retry


class TestException(Exception):
    """Test exception."""


def test_retry_on_exception_success_first_try():
    """Test successful execution on first try."""
    call_count = 0

    @retry_on_exception(max_attempts=3)
    def func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = func()
    assert result == "success"
    assert call_count == 1


def test_retry_on_exception_success_after_retries():
    """Test successful execution after retries."""
    call_count = 0

    @retry_on_exception(exceptions=(TestException,), max_attempts=3, min_wait=0.01, max_wait=0.1)
    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TestException("Temporary error")
        return "success"

    result = func()
    assert result == "success"
    assert call_count == 3


def test_retry_on_exception_exhausted():
    """Test retry exhaustion."""

    @retry_on_exception(exceptions=(TestException,), max_attempts=3, min_wait=0.01, max_wait=0.1)
    def func():
        raise TestException("Persistent error")

    with pytest.raises(TestException, match="Persistent error"):
        func()


def test_retry_on_exception_wrong_exception_type():
    """Test that wrong exception types are not retried."""

    @retry_on_exception(exceptions=(TestException,), max_attempts=3)
    def func():
        raise ValueError("Different error")

    with pytest.raises(ValueError, match="Different error"):
        func()


def test_simple_retry_success_first_try():
    """Test simple retry with immediate success."""
    call_count = 0

    def func():
        nonlocal call_count
        call_count += 1
        return "success"

    wrapped = simple_retry(func, max_attempts=3, delay=0.01)
    result = wrapped()
    assert result == "success"
    assert call_count == 1


def test_simple_retry_success_after_failures():
    """Test simple retry with success after failures."""
    call_count = 0

    def func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TestException("Temporary")
        return "success"

    wrapped = simple_retry(func, max_attempts=3, delay=0.01, exceptions=(TestException,))
    result = wrapped()
    assert result == "success"
    assert call_count == 2


def test_simple_retry_exhausted():
    """Test simple retry exhaustion."""

    def func():
        raise TestException("Always fails")

    wrapped = simple_retry(func, max_attempts=3, delay=0.01, exceptions=(TestException,))

    with pytest.raises(TestException, match="Always fails"):
        wrapped()


def test_simple_retry_with_args_and_kwargs():
    """Test simple retry preserves args and kwargs."""

    def func(a, b, c=None):
        return f"{a}-{b}-{c}"

    wrapped = simple_retry(func, max_attempts=2)
    result = wrapped("x", "y", c="z")
    assert result == "x-y-z"


def test_simple_retry_backoff():
    """Test that backoff increases delay."""
    import time

    call_count = 0
    call_times = []

    def func():
        nonlocal call_count
        call_count += 1
        call_times.append(time.time())
        raise TestException("Always fails")

    wrapped = simple_retry(
        func,
        max_attempts=3,
        delay=0.1,
        backoff=2.0,
        exceptions=(TestException,),
    )

    with pytest.raises(TestException):
        wrapped()

    assert call_count == 3
    assert len(call_times) == 3

    # First to second call should have ~0.1s delay
    # Second to third call should have ~0.2s delay (backoff 2.0)
    delay1 = call_times[1] - call_times[0]
    delay2 = call_times[2] - call_times[1]

    assert 0.08 < delay1 < 0.15  # Allow some timing variance
    assert 0.18 < delay2 < 0.25
