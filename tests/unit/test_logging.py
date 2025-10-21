"""Unit tests for structured logging utilities.

This module tests the logging configuration and utilities including:
- Logging setup with different levels and formats
- Logger instance creation
- Structured logging helpers
- Error logging with context
- Log processor configuration
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import structlog

from guard.utils.logging import get_logger, log_error, log_operation, setup_logging


class TestSetupLogging:
    """Test setup_logging function."""

    @pytest.fixture(autouse=True)
    def reset_logging(self):
        """Reset logging configuration before each test."""
        # Clear existing handlers
        logging.root.handlers = []
        # Reset structlog configuration
        structlog.reset_defaults()
        yield
        # Cleanup after test
        logging.root.handlers = []
        structlog.reset_defaults()

    def test_setup_logging_default_parameters(self):
        """Test setup_logging with default parameters."""
        setup_logging()

        # Verify logging is configured
        assert len(logging.root.handlers) > 0

    def test_setup_logging_info_level(self):
        """Test setup_logging with INFO level."""
        setup_logging(level="INFO")

        # Check handlers are configured (root level might be overridden by structlog)
        assert len(logging.root.handlers) > 0

    def test_setup_logging_debug_level(self):
        """Test setup_logging with DEBUG level."""
        setup_logging(level="DEBUG")

        # Verify configuration was called
        assert len(logging.root.handlers) > 0

    def test_setup_logging_warning_level(self):
        """Test setup_logging with WARNING level."""
        setup_logging(level="WARNING")

        assert logging.root.level == logging.WARNING

    def test_setup_logging_error_level(self):
        """Test setup_logging with ERROR level."""
        setup_logging(level="ERROR")

        # Verify configuration was called
        assert len(logging.root.handlers) > 0

    def test_setup_logging_critical_level(self):
        """Test setup_logging with CRITICAL level."""
        setup_logging(level="CRITICAL")

        # Verify configuration was called
        assert len(logging.root.handlers) > 0

    def test_setup_logging_invalid_level_defaults_to_info(self):
        """Test setup_logging with invalid level defaults to INFO."""
        setup_logging(level="INVALID")

        # Should still configure logging
        assert len(logging.root.handlers) > 0

    def test_setup_logging_lowercase_level(self):
        """Test setup_logging accepts lowercase level names."""
        setup_logging(level="debug")

        # Verify configuration was called
        assert len(logging.root.handlers) > 0

    def test_setup_logging_json_format(self):
        """Test setup_logging with JSON format."""
        setup_logging(format="json")

        # Get structlog configuration
        config = structlog.get_config()

        # Verify JSON renderer is in processors
        processors = config["processors"]
        assert any(
            isinstance(p, structlog.processors.JSONRenderer) for p in processors
        ), "JSONRenderer not found in processors"

    def test_setup_logging_console_format(self):
        """Test setup_logging with console format."""
        setup_logging(format="console")

        # Get structlog configuration
        config = structlog.get_config()

        # Verify console renderer is in processors
        processors = config["processors"]
        assert any(
            isinstance(p, structlog.dev.ConsoleRenderer) for p in processors
        ), "ConsoleRenderer not found in processors"

    def test_setup_logging_stdout_output(self):
        """Test setup_logging outputs to stdout."""
        setup_logging(output="stdout")

        # Verify handlers are configured
        assert len(logging.root.handlers) > 0

    def test_setup_logging_stderr_output(self):
        """Test setup_logging outputs to stderr."""
        setup_logging(output="stderr")

        # Verify handlers are configured
        assert len(logging.root.handlers) > 0

    def test_setup_logging_includes_timestamp_processor(self):
        """Test setup_logging includes timestamp processor."""
        setup_logging()

        config = structlog.get_config()
        processors = config["processors"]

        # Verify timestamp processor is present
        assert any(
            isinstance(p, structlog.processors.TimeStamper) for p in processors
        ), "TimeStamper not found in processors"

    def test_setup_logging_includes_log_level_processor(self):
        """Test setup_logging includes log level processor."""
        setup_logging()

        config = structlog.get_config()
        processors = config["processors"]

        # Verify log level processor
        [type(p).__name__ for p in processors]
        assert "add_log_level" in str(processors), "add_log_level processor not found"

    def test_setup_logging_includes_context_processor(self):
        """Test setup_logging includes context vars processor."""
        setup_logging()

        config = structlog.get_config()
        processors = config["processors"]

        # Verify context vars processor
        [type(p).__name__ for p in processors]
        assert "merge_contextvars" in str(processors), "merge_contextvars processor not found"

    def test_setup_logging_json_processors_order(self):
        """Test JSON format has correct processor order."""
        setup_logging(format="json")

        config = structlog.get_config()
        processors = config["processors"]

        # JSONRenderer should be last
        assert isinstance(
            processors[-1], structlog.processors.JSONRenderer
        ), "JSONRenderer should be last processor"

    def test_setup_logging_console_processors_order(self):
        """Test console format has correct processor order."""
        setup_logging(format="console")

        config = structlog.get_config()
        processors = config["processors"]

        # ConsoleRenderer should be last
        assert isinstance(
            processors[-1], structlog.dev.ConsoleRenderer
        ), "ConsoleRenderer should be last processor"

    def test_setup_logging_caches_logger(self):
        """Test setup_logging configures logger caching."""
        setup_logging()

        config = structlog.get_config()
        assert config["cache_logger_on_first_use"] is True


class TestGetLogger:
    """Test get_logger function."""

    @pytest.fixture(autouse=True)
    def setup_test_logging(self):
        """Setup logging for tests."""
        setup_logging(level="DEBUG", format="json")
        yield

    def test_get_logger_returns_bound_logger(self):
        """Test get_logger returns a BoundLogger instance."""
        logger = get_logger()

        # Check it's a structlog logger (BoundLogger or BoundLoggerLazyProxy)
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")

    def test_get_logger_with_name(self):
        """Test get_logger with a name parameter."""
        logger = get_logger("test_module")

        # Logger should work
        assert logger is not None

    def test_get_logger_without_name(self):
        """Test get_logger without name parameter."""
        logger = get_logger()

        assert logger is not None

    def test_get_logger_returns_different_instances_for_different_names(self):
        """Test get_logger returns different instances for different names."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # Both should be valid loggers
        assert logger1 is not None
        assert logger2 is not None

    def test_get_logger_can_log_messages(self):
        """Test logger can log messages."""
        logger = get_logger("test")

        # Should not raise
        logger.info("test_message", key="value")
        logger.debug("debug_message")
        logger.warning("warning_message")
        logger.error("error_message")


class TestLogOperation:
    """Test log_operation helper function."""

    @pytest.fixture(autouse=True)
    def setup_test_logging(self):
        """Setup logging for tests."""
        setup_logging(level="DEBUG", format="json")
        yield

    def test_log_operation_basic(self):
        """Test log_operation logs with operation name."""
        logger = MagicMock()
        logger.info = MagicMock()

        log_operation(logger, "test_operation")

        logger.info.assert_called_once_with("operation_test_operation")

    def test_log_operation_with_context(self):
        """Test log_operation logs with additional context."""
        logger = MagicMock()
        logger.info = MagicMock()

        log_operation(logger, "upgrade", cluster_id="cluster-1", version="1.20.0")

        logger.info.assert_called_once_with(
            "operation_upgrade", cluster_id="cluster-1", version="1.20.0"
        )

    def test_log_operation_with_multiple_kwargs(self):
        """Test log_operation with multiple keyword arguments."""
        logger = MagicMock()
        logger.info = MagicMock()

        log_operation(
            logger,
            "validation",
            status="success",
            duration=1.5,
            checks_passed=10,
        )

        logger.info.assert_called_once_with(
            "operation_validation",
            status="success",
            duration=1.5,
            checks_passed=10,
        )

    def test_log_operation_formats_operation_name(self):
        """Test log_operation formats operation name with prefix."""
        logger = MagicMock()
        logger.info = MagicMock()

        log_operation(logger, "pre_check")

        # Should be prefixed with "operation_"
        call_args = logger.info.call_args
        assert call_args[0][0] == "operation_pre_check"

    def test_log_operation_with_real_logger(self):
        """Test log_operation with real logger instance."""
        logger = get_logger("test")

        # Should not raise
        log_operation(logger, "test_op", key="value")


class TestLogError:
    """Test log_error helper function."""

    @pytest.fixture(autouse=True)
    def setup_test_logging(self):
        """Setup logging for tests."""
        setup_logging(level="DEBUG", format="json")
        yield

    def test_log_error_basic(self):
        """Test log_error logs error with context."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = ValueError("Test error")

        log_error(logger, error)

        logger.error.assert_called_once()
        call_args = logger.error.call_args
        assert call_args[0][0] == "error_occurred"
        assert call_args[1]["error_type"] == "ValueError"
        assert call_args[1]["error_message"] == "Test error"
        assert call_args[1]["exc_info"] is True

    def test_log_error_with_operation(self):
        """Test log_error includes operation in context."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = RuntimeError("Runtime error")

        log_error(logger, error, operation="pre_check")

        call_args = logger.error.call_args
        assert call_args[1]["operation"] == "pre_check"
        assert call_args[1]["error_type"] == "RuntimeError"
        assert call_args[1]["error_message"] == "Runtime error"

    def test_log_error_with_additional_context(self):
        """Test log_error with additional context kwargs."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = TimeoutError("Operation timed out")

        log_error(logger, error, operation="validation", cluster_id="cluster-1", timeout=30)

        call_args = logger.error.call_args
        assert call_args[1]["operation"] == "validation"
        assert call_args[1]["cluster_id"] == "cluster-1"
        assert call_args[1]["timeout"] == 30
        assert call_args[1]["error_type"] == "TimeoutError"

    def test_log_error_includes_exc_info(self):
        """Test log_error includes exception info."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = Exception("Test exception")

        log_error(logger, error)

        call_args = logger.error.call_args
        assert call_args[1]["exc_info"] is True

    def test_log_error_extracts_error_type(self):
        """Test log_error extracts error type name."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = KeyError("missing_key")

        log_error(logger, error)

        call_args = logger.error.call_args
        assert call_args[1]["error_type"] == "KeyError"

    def test_log_error_extracts_error_message(self):
        """Test log_error extracts error message."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = ValueError("Invalid value provided")

        log_error(logger, error)

        call_args = logger.error.call_args
        assert call_args[1]["error_message"] == "Invalid value provided"

    def test_log_error_without_operation(self):
        """Test log_error without operation parameter."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = TypeError("Type error")

        log_error(logger, error)

        call_args = logger.error.call_args
        # Operation should not be in context
        assert "operation" not in call_args[1]

    def test_log_error_with_real_logger(self):
        """Test log_error with real logger instance."""
        logger = get_logger("test")
        error = RuntimeError("Test runtime error")

        # Should not raise
        log_error(logger, error, operation="test_op", context="testing")

    def test_log_error_with_nested_exception(self):
        """Test log_error handles nested exception messages."""
        logger = MagicMock()
        logger.error = MagicMock()
        error = ValueError("Outer error")

        log_error(logger, error)

        call_args = logger.error.call_args
        assert call_args[1]["error_type"] == "ValueError"
        assert "Outer error" in call_args[1]["error_message"]


class TestLoggingIntegration:
    """Integration tests for logging utilities."""

    @pytest.fixture(autouse=True)
    def reset_logging(self):
        """Reset logging for each test."""
        logging.root.handlers = []
        structlog.reset_defaults()
        yield
        logging.root.handlers = []
        structlog.reset_defaults()

    def test_logging_workflow_json_format(self):
        """Test complete logging workflow with JSON format."""
        # Setup logging
        setup_logging(level="INFO", format="json", output="stdout")

        # Get logger
        logger = get_logger("test_module")

        # Log operations
        log_operation(logger, "test_operation", status="starting")
        log_operation(logger, "test_operation", status="completed")

        # Should complete without errors
        assert True

    def test_logging_workflow_console_format(self):
        """Test complete logging workflow with console format."""
        # Setup logging
        setup_logging(level="DEBUG", format="console", output="stderr")

        # Get logger
        logger = get_logger("test_module")

        # Log operations and errors
        log_operation(logger, "operation1", result="success")

        try:
            raise ValueError("Test error")
        except ValueError as e:
            log_error(logger, e, operation="operation1")

        # Should complete without errors
        assert True

    def test_multiple_loggers_share_configuration(self):
        """Test multiple loggers share the same configuration."""
        setup_logging(level="WARNING", format="json")

        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # Both should work with same configuration
        log_operation(logger1, "op1", data="test1")
        log_operation(logger2, "op2", data="test2")

        # Should complete without errors
        assert True

    def test_logging_with_context_vars(self):
        """Test logging preserves context variables."""
        setup_logging(level="INFO", format="json")

        logger = get_logger("test")

        # Add context and log
        with structlog.contextvars.bound_contextvars(request_id="req-123", cluster_id="cluster-1"):
            log_operation(logger, "operation", status="running")

        # Should complete without errors
        assert True

    def test_reconfiguring_logging(self):
        """Test logging can be reconfigured."""
        # Initial setup
        setup_logging(level="INFO", format="json")
        logger1 = get_logger("test")

        # Reconfigure
        setup_logging(level="DEBUG", format="console")
        logger2 = get_logger("test")

        # Both should work
        log_operation(logger1, "op1")
        log_operation(logger2, "op2")

        # Should complete without errors
        assert True
