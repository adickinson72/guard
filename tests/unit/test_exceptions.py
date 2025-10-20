"""Unit tests for custom exceptions."""

import pytest

from guard.core.exceptions import (
    AWSError,
    ClusterNotFoundError,
    ConfigurationError,
    DatadogError,
    GitOpsError,
    IguError,
    IstioError,
    KubernetesError,
    LockAcquisitionError,
    PreCheckFailedError,
    RollbackError,
    ValidationFailedError,
)


class TestExceptionHierarchy:
    """Tests for exception hierarchy and inheritance."""

    def test_all_exceptions_inherit_from_igu_error(self) -> None:
        """Test that all custom exceptions inherit from IguError."""
        exceptions = [
            ConfigurationError,
            PreCheckFailedError,
            ValidationFailedError,
            ClusterNotFoundError,
            GitOpsError,
            AWSError,
            DatadogError,
            KubernetesError,
            IstioError,
            RollbackError,
            LockAcquisitionError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, IguError)

    def test_igu_error_inherits_from_exception(self) -> None:
        """Test that IguError inherits from Exception."""
        assert issubclass(IguError, Exception)

    def test_can_catch_with_base_exception(self) -> None:
        """Test that specific exceptions can be caught with IguError."""
        with pytest.raises(IguError):
            raise ConfigurationError("Test error")

        with pytest.raises(IguError):
            raise ValidationFailedError("Test error")

    def test_exception_messages(self) -> None:
        """Test that exception messages are preserved."""
        error_message = "This is a test error message"
        exc = ConfigurationError(error_message)

        assert str(exc) == error_message

    def test_raising_specific_exceptions(self) -> None:
        """Test raising and catching specific exception types."""
        with pytest.raises(PreCheckFailedError) as exc_info:
            raise PreCheckFailedError("Pre-check failed: nodes not ready")

        assert "Pre-check failed" in str(exc_info.value)

        with pytest.raises(ValidationFailedError) as exc_info:
            raise ValidationFailedError("P99 latency increased by 45%")

        assert "latency" in str(exc_info.value)
