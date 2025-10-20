"""Structured logging utilities for IGU."""

import logging
import sys
from typing import Any

import structlog


def setup_logging(level: str = "INFO", format: str = "json", output: str = "stdout") -> None:
    """Configure structured logging for IGU.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Log format (json or console)
        output: Output destination (stdout or stderr)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout if output == "stdout" else sys.stderr,
        level=log_level,
    )

    # Configure processors based on format
    if format == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


def log_operation(
    logger: structlog.BoundLogger,
    operation: str,
    **kwargs: Any,
) -> None:
    """Log an operation with structured context.

    Args:
        logger: Logger instance
        operation: Operation name
        **kwargs: Additional context fields
    """
    logger.info(f"operation_{operation}", **kwargs)


def log_error(
    logger: structlog.BoundLogger,
    error: Exception,
    operation: str | None = None,
    **kwargs: Any,
) -> None:
    """Log an error with structured context.

    Args:
        logger: Logger instance
        error: Exception instance
        operation: Operation name (optional)
        **kwargs: Additional context fields
    """
    context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        **kwargs,
    }

    if operation:
        context["operation"] = operation

    logger.error("error_occurred", **context, exc_info=True)
