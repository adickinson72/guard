"""Unit tests for rate limiter initialization from configuration.

This module tests the rate limiter initialization utilities including:
- Initialization from GuardConfig
- Initialization from RateLimitsConfig
- Rate limiter registration
- Configuration conversion (requests per minute to per second)
- Multiple rate limiter setup
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from guard.core.config import AWSConfig, GitLabConfig, GuardConfig, RateLimitsConfig
from guard.utils.rate_limiter_init import (
    initialize_rate_limiters,
    initialize_rate_limiters_from_config,
)


class TestInitializeRateLimiters:
    """Test initialize_rate_limiters function."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        with patch("guard.utils.rate_limiter_init.get_rate_limiter") as mock:
            limiter = MagicMock()
            mock.return_value = limiter
            yield limiter

    @pytest.fixture
    def sample_guard_config(self):
        """Create a sample GuardConfig for testing."""
        return GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
            rate_limits=RateLimitsConfig(
                gitlab_api=300,
                datadog_api=300,
                aws_api=100,
            ),
        )

    def test_initialize_rate_limiters_registers_gitlab_limiter(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization registers GitLab rate limiter."""
        initialize_rate_limiters(sample_guard_config)

        # Verify GitLab limiter was registered
        calls = mock_rate_limiter.register.call_args_list
        gitlab_call = next(c for c in calls if c[1]["name"] == "gitlab_api")

        assert gitlab_call[1]["name"] == "gitlab_api"
        assert gitlab_call[1]["capacity"] == 300
        assert gitlab_call[1]["refill_rate"] == 5.0  # 300 / 60
        assert gitlab_call[1]["max_wait"] == 120.0

    def test_initialize_rate_limiters_registers_datadog_limiter(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization registers Datadog rate limiter."""
        initialize_rate_limiters(sample_guard_config)

        # Verify Datadog limiter was registered
        calls = mock_rate_limiter.register.call_args_list
        datadog_call = next(c for c in calls if c[1]["name"] == "datadog_api")

        assert datadog_call[1]["name"] == "datadog_api"
        assert datadog_call[1]["capacity"] == 300
        assert datadog_call[1]["refill_rate"] == 5.0  # 300 / 60
        assert datadog_call[1]["max_wait"] == 120.0

    def test_initialize_rate_limiters_registers_aws_limiter(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization registers AWS rate limiter."""
        initialize_rate_limiters(sample_guard_config)

        # Verify AWS limiter was registered
        calls = mock_rate_limiter.register.call_args_list
        aws_call = next(c for c in calls if c[1]["name"] == "aws_api")

        assert aws_call[1]["name"] == "aws_api"
        assert aws_call[1]["capacity"] == 100
        assert aws_call[1]["refill_rate"] == 100 / 60.0  # 100 / 60
        assert aws_call[1]["max_wait"] == 120.0

    def test_initialize_rate_limiters_registers_all_three_limiters(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization registers all three rate limiters."""
        initialize_rate_limiters(sample_guard_config)

        # Should have registered 3 limiters
        assert mock_rate_limiter.register.call_count == 3

        # Verify all three names
        call_names = [c[1]["name"] for c in mock_rate_limiter.register.call_args_list]
        assert "gitlab_api" in call_names
        assert "datadog_api" in call_names
        assert "aws_api" in call_names

    def test_initialize_rate_limiters_converts_rate_per_minute_to_per_second(
        self, mock_rate_limiter
    ):
        """Test rate conversion from per-minute to per-second."""
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
            rate_limits=RateLimitsConfig(
                gitlab_api=600,  # 600 per minute = 10 per second
                datadog_api=120,  # 120 per minute = 2 per second
                aws_api=60,  # 60 per minute = 1 per second
            ),
        )

        initialize_rate_limiters(config)

        calls = {
            c[1]["name"]: c[1]["refill_rate"] for c in mock_rate_limiter.register.call_args_list
        }

        assert calls["gitlab_api"] == 10.0
        assert calls["datadog_api"] == 2.0
        assert calls["aws_api"] == 1.0

    def test_initialize_rate_limiters_with_custom_rates(self, mock_rate_limiter):
        """Test initialization with custom rate limits."""
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
            rate_limits=RateLimitsConfig(
                gitlab_api=450,
                datadog_api=200,
                aws_api=50,
            ),
        )

        initialize_rate_limiters(config)

        calls = {c[1]["name"]: c[1] for c in mock_rate_limiter.register.call_args_list}

        assert calls["gitlab_api"]["capacity"] == 450
        assert calls["gitlab_api"]["refill_rate"] == 7.5  # 450 / 60
        assert calls["datadog_api"]["capacity"] == 200
        assert calls["datadog_api"]["refill_rate"] == 200 / 60.0
        assert calls["aws_api"]["capacity"] == 50
        assert calls["aws_api"]["refill_rate"] == 50 / 60.0

    def test_initialize_rate_limiters_uses_2_minute_max_wait(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test all limiters use 2 minute (120 second) max wait."""
        initialize_rate_limiters(sample_guard_config)

        # All limiters should have 120 second max wait
        for call_args in mock_rate_limiter.register.call_args_list:
            assert call_args[1]["max_wait"] == 120.0

    @patch("guard.utils.rate_limiter_init.logger")
    def test_initialize_rate_limiters_logs_initialization(
        self, mock_logger, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization logs start and completion."""
        initialize_rate_limiters(sample_guard_config)

        # Should log start and completion
        assert mock_logger.info.call_count == 2
        log_calls = [c[0][0] for c in mock_logger.info.call_args_list]
        assert "initializing_rate_limiters" in log_calls
        assert "rate_limiters_initialized" in log_calls

    @patch("guard.utils.rate_limiter_init.logger")
    def test_initialize_rate_limiters_logs_config_details(
        self, mock_logger, mock_rate_limiter, sample_guard_config
    ):
        """Test initialization logs configuration details."""
        initialize_rate_limiters(sample_guard_config)

        # First log call should include limits
        first_call = mock_logger.info.call_args_list[0]
        assert first_call[0][0] == "initializing_rate_limiters"
        assert "limits" in first_call[1]

    def test_initialize_rate_limiters_with_default_config(self, mock_rate_limiter):
        """Test initialization with default configuration values."""
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
        )  # Uses default rate limits

        initialize_rate_limiters(config)

        # Should still register all three limiters
        assert mock_rate_limiter.register.call_count == 3

    def test_initialize_rate_limiters_registration_order(
        self, mock_rate_limiter, sample_guard_config
    ):
        """Test limiters are registered in expected order."""
        initialize_rate_limiters(sample_guard_config)

        # Get registration order
        call_order = [c[1]["name"] for c in mock_rate_limiter.register.call_args_list]

        assert call_order == ["gitlab_api", "datadog_api", "aws_api"]


class TestInitializeRateLimitersFromConfig:
    """Test initialize_rate_limiters_from_config function."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        with patch("guard.utils.rate_limiter_init.get_rate_limiter") as mock:
            limiter = MagicMock()
            mock.return_value = limiter
            yield limiter

    @pytest.fixture
    def sample_rate_limits_config(self):
        """Create a sample RateLimitsConfig for testing."""
        return RateLimitsConfig(
            gitlab_api=300,
            datadog_api=300,
            aws_api=100,
        )

    def test_initialize_from_config_registers_gitlab_limiter(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct config initialization registers GitLab limiter."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        calls = mock_rate_limiter.register.call_args_list
        gitlab_call = next(c for c in calls if c[1]["name"] == "gitlab_api")

        assert gitlab_call[1]["capacity"] == 300
        assert gitlab_call[1]["refill_rate"] == 5.0

    def test_initialize_from_config_registers_datadog_limiter(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct config initialization registers Datadog limiter."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        calls = mock_rate_limiter.register.call_args_list
        datadog_call = next(c for c in calls if c[1]["name"] == "datadog_api")

        assert datadog_call[1]["capacity"] == 300
        assert datadog_call[1]["refill_rate"] == 5.0

    def test_initialize_from_config_registers_aws_limiter(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct config initialization registers AWS limiter."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        calls = mock_rate_limiter.register.call_args_list
        aws_call = next(c for c in calls if c[1]["name"] == "aws_api")

        assert aws_call[1]["capacity"] == 100
        assert aws_call[1]["refill_rate"] == 100 / 60.0

    def test_initialize_from_config_registers_all_three_limiters(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct config initialization registers all limiters."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        assert mock_rate_limiter.register.call_count == 3

        call_names = [c[1]["name"] for c in mock_rate_limiter.register.call_args_list]
        assert set(call_names) == {"gitlab_api", "datadog_api", "aws_api"}

    def test_initialize_from_config_with_custom_rates(self, mock_rate_limiter):
        """Test direct initialization with custom rate limits."""
        rate_limits = RateLimitsConfig(
            gitlab_api=500,
            datadog_api=250,
            aws_api=75,
        )

        initialize_rate_limiters_from_config(rate_limits)

        calls = {c[1]["name"]: c[1] for c in mock_rate_limiter.register.call_args_list}

        assert calls["gitlab_api"]["capacity"] == 500
        assert calls["gitlab_api"]["refill_rate"] == 500 / 60.0
        assert calls["datadog_api"]["capacity"] == 250
        assert calls["datadog_api"]["refill_rate"] == 250 / 60.0
        assert calls["aws_api"]["capacity"] == 75
        assert calls["aws_api"]["refill_rate"] == 75 / 60.0

    def test_initialize_from_config_uses_120_second_max_wait(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct initialization uses 120 second max wait."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        for call_args in mock_rate_limiter.register.call_args_list:
            assert call_args[1]["max_wait"] == 120.0

    @patch("guard.utils.rate_limiter_init.logger")
    def test_initialize_from_config_logs_initialization(
        self, mock_logger, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct initialization logs properly."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        # Should log start and completion
        assert mock_logger.info.call_count == 2
        log_calls = [c[0][0] for c in mock_logger.info.call_args_list]
        assert "initializing_rate_limiters_direct" in log_calls
        assert "rate_limiters_initialized" in log_calls

    @patch("guard.utils.rate_limiter_init.logger")
    def test_initialize_from_config_logs_limits(
        self, mock_logger, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct initialization logs rate limits."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        first_call = mock_logger.info.call_args_list[0]
        assert first_call[0][0] == "initializing_rate_limiters_direct"
        assert "limits" in first_call[1]

    def test_initialize_from_config_registration_order(
        self, mock_rate_limiter, sample_rate_limits_config
    ):
        """Test direct initialization registers in expected order."""
        initialize_rate_limiters_from_config(sample_rate_limits_config)

        call_order = [c[1]["name"] for c in mock_rate_limiter.register.call_args_list]
        assert call_order == ["gitlab_api", "datadog_api", "aws_api"]


class TestRateLimiterInitializationIntegration:
    """Integration tests for rate limiter initialization."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter that tracks registrations."""
        with patch("guard.utils.rate_limiter_init.get_rate_limiter") as mock:
            limiter = MagicMock()
            limiter.registered_limiters = {}

            def register_side_effect(name, capacity, refill_rate, max_wait):
                limiter.registered_limiters[name] = {
                    "capacity": capacity,
                    "refill_rate": refill_rate,
                    "max_wait": max_wait,
                }

            limiter.register.side_effect = register_side_effect
            mock.return_value = limiter
            yield limiter

    def test_both_initialization_methods_produce_same_result(self, mock_rate_limiter):
        """Test both initialization methods produce identical configuration."""
        rate_limits = RateLimitsConfig(gitlab_api=400, datadog_api=350, aws_api=80)

        # Method 1: From GuardConfig
        guard_config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
            rate_limits=rate_limits,
        )
        initialize_rate_limiters(guard_config)
        result1 = mock_rate_limiter.registered_limiters.copy()

        # Reset
        mock_rate_limiter.registered_limiters.clear()
        mock_rate_limiter.register.reset_mock()

        # Method 2: From RateLimitsConfig directly
        initialize_rate_limiters_from_config(rate_limits)
        result2 = mock_rate_limiter.registered_limiters.copy()

        # Both methods should produce identical results
        assert result1 == result2

    def test_initialization_with_minimal_config(self, mock_rate_limiter):
        """Test initialization works with minimal configuration."""
        # Use default values
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
        )

        initialize_rate_limiters(config)

        # Should have registered all three limiters
        assert len(mock_rate_limiter.registered_limiters) == 3
        assert "gitlab_api" in mock_rate_limiter.registered_limiters
        assert "datadog_api" in mock_rate_limiter.registered_limiters
        assert "aws_api" in mock_rate_limiter.registered_limiters

    def test_initialization_with_high_rate_limits(self, mock_rate_limiter):
        """Test initialization with very high rate limits."""
        rate_limits = RateLimitsConfig(
            gitlab_api=6000,  # 100 per second
            datadog_api=12000,  # 200 per second
            aws_api=3000,  # 50 per second
        )

        initialize_rate_limiters_from_config(rate_limits)

        assert mock_rate_limiter.registered_limiters["gitlab_api"]["refill_rate"] == 100.0
        assert mock_rate_limiter.registered_limiters["datadog_api"]["refill_rate"] == 200.0
        assert mock_rate_limiter.registered_limiters["aws_api"]["refill_rate"] == 50.0

    def test_initialization_with_low_rate_limits(self, mock_rate_limiter):
        """Test initialization with very low rate limits."""
        rate_limits = RateLimitsConfig(
            gitlab_api=10,  # ~0.167 per second
            datadog_api=20,  # ~0.333 per second
            aws_api=5,  # ~0.083 per second
        )

        initialize_rate_limiters_from_config(rate_limits)

        # Verify fractional refill rates
        assert (
            abs(mock_rate_limiter.registered_limiters["gitlab_api"]["refill_rate"] - 10 / 60.0)
            < 0.001
        )
        assert (
            abs(mock_rate_limiter.registered_limiters["datadog_api"]["refill_rate"] - 20 / 60.0)
            < 0.001
        )
        assert (
            abs(mock_rate_limiter.registered_limiters["aws_api"]["refill_rate"] - 5 / 60.0) < 0.001
        )

    def test_multiple_initialization_attempts(self, mock_rate_limiter):
        """Test multiple initialization attempts (idempotency)."""
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
        )

        # Initialize twice
        initialize_rate_limiters(config)
        initialize_rate_limiters(config)

        # Should have attempted to register 6 times (3 limiters x 2 calls)
        assert mock_rate_limiter.register.call_count == 6

    def test_initialization_preserves_capacity_equals_tokens(self, mock_rate_limiter):
        """Test that capacity matches the configured requests per minute."""
        rate_limits = RateLimitsConfig(
            gitlab_api=300,
            datadog_api=450,
            aws_api=150,
        )

        initialize_rate_limiters_from_config(rate_limits)

        # Capacity should match original per-minute values
        assert mock_rate_limiter.registered_limiters["gitlab_api"]["capacity"] == 300
        assert mock_rate_limiter.registered_limiters["datadog_api"]["capacity"] == 450
        assert mock_rate_limiter.registered_limiters["aws_api"]["capacity"] == 150

    def test_initialization_with_default_guard_config(self, mock_rate_limiter):
        """Test initialization using completely default GuardConfig."""
        config = GuardConfig(
            aws=AWSConfig(region="us-east-1"),
            gitlab=GitLabConfig(url="https://gitlab.example.com"),
        )

        initialize_rate_limiters(config)

        # Verify default values are used (from RateLimitsConfig defaults)
        assert mock_rate_limiter.registered_limiters["gitlab_api"]["capacity"] == 300
        assert mock_rate_limiter.registered_limiters["datadog_api"]["capacity"] == 300
        assert mock_rate_limiter.registered_limiters["aws_api"]["capacity"] == 100


class TestRateLimiterInitializationEdgeCases:
    """Test edge cases in rate limiter initialization."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        with patch("guard.utils.rate_limiter_init.get_rate_limiter") as mock:
            limiter = MagicMock()
            mock.return_value = limiter
            yield limiter

    def test_initialization_with_very_small_rates(self, mock_rate_limiter):
        """Test initialization with rates less than 1 per second."""
        rate_limits = RateLimitsConfig(
            gitlab_api=30,  # 0.5 per second
            datadog_api=15,  # 0.25 per second
            aws_api=6,  # 0.1 per second
        )

        initialize_rate_limiters_from_config(rate_limits)

        calls = {c[1]["name"]: c[1] for c in mock_rate_limiter.register.call_args_list}

        # Verify fractional rates
        assert calls["gitlab_api"]["refill_rate"] == 0.5
        assert calls["datadog_api"]["refill_rate"] == 0.25
        assert calls["aws_api"]["refill_rate"] == 0.1

    def test_initialization_rate_conversion_accuracy(self, mock_rate_limiter):
        """Test rate conversion maintains accuracy."""
        rate_limits = RateLimitsConfig(
            gitlab_api=333,  # Odd number to test precision
            datadog_api=277,
            aws_api=111,
        )

        initialize_rate_limiters_from_config(rate_limits)

        calls = {c[1]["name"]: c[1] for c in mock_rate_limiter.register.call_args_list}

        # Verify conversion accuracy
        assert abs(calls["gitlab_api"]["refill_rate"] - 333 / 60.0) < 0.0001
        assert abs(calls["datadog_api"]["refill_rate"] - 277 / 60.0) < 0.0001
        assert abs(calls["aws_api"]["refill_rate"] - 111 / 60.0) < 0.0001
