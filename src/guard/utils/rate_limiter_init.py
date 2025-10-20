"""Initialize rate limiters from configuration."""

from guard.core.config import GuardConfig, RateLimitsConfig
from guard.utils.logging import get_logger
from guard.utils.rate_limiter import get_rate_limiter

logger = get_logger(__name__)


def initialize_rate_limiters(config: GuardConfig) -> None:
    """Initialize rate limiters from configuration.

    This function should be called once at application startup to register
    all rate limiters with their configured limits.

    Args:
        config: GUARD configuration containing rate limit settings
    """
    rate_limiter = get_rate_limiter()
    rate_limits = config.rate_limits

    logger.info("initializing_rate_limiters", limits=rate_limits.model_dump())

    # GitLab API rate limiter (requests per minute)
    rate_limiter.register(
        name="gitlab_api",
        capacity=rate_limits.gitlab_api,
        refill_rate=rate_limits.gitlab_api / 60.0,  # Convert to requests per second
        max_wait=120.0,  # 2 minutes max wait
    )

    # Datadog API rate limiter (requests per minute)
    rate_limiter.register(
        name="datadog_api",
        capacity=rate_limits.datadog_api,
        refill_rate=rate_limits.datadog_api / 60.0,  # Convert to requests per second
        max_wait=120.0,  # 2 minutes max wait
    )

    # AWS API rate limiter (requests per minute)
    rate_limiter.register(
        name="aws_api",
        capacity=rate_limits.aws_api,
        refill_rate=rate_limits.aws_api / 60.0,  # Convert to requests per second
        max_wait=120.0,  # 2 minutes max wait
    )

    logger.info("rate_limiters_initialized")


def initialize_rate_limiters_from_config(rate_limits: RateLimitsConfig) -> None:
    """Initialize rate limiters directly from RateLimitsConfig.

    Convenience function when you have RateLimitsConfig but not full GuardConfig.

    Args:
        rate_limits: Rate limits configuration
    """
    rate_limiter = get_rate_limiter()

    logger.info("initializing_rate_limiters_direct", limits=rate_limits.model_dump())

    # GitLab API rate limiter
    rate_limiter.register(
        name="gitlab_api",
        capacity=rate_limits.gitlab_api,
        refill_rate=rate_limits.gitlab_api / 60.0,
        max_wait=120.0,
    )

    # Datadog API rate limiter
    rate_limiter.register(
        name="datadog_api",
        capacity=rate_limits.datadog_api,
        refill_rate=rate_limits.datadog_api / 60.0,
        max_wait=120.0,
    )

    # AWS API rate limiter
    rate_limiter.register(
        name="aws_api",
        capacity=rate_limits.aws_api,
        refill_rate=rate_limits.aws_api / 60.0,
        max_wait=120.0,
    )

    logger.info("rate_limiters_initialized")
