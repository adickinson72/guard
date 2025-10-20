"""Exceptions for interface implementations."""


class InterfaceError(Exception):
    """Base exception for all interface-related errors."""


class CloudProviderError(InterfaceError):
    """Exception for cloud provider operations."""


class KubernetesProviderError(InterfaceError):
    """Exception for Kubernetes provider operations."""


class MetricsProviderError(InterfaceError):
    """Exception for metrics provider operations."""


class GitOpsProviderError(InterfaceError):
    """Exception for GitOps provider operations."""


class StateStoreError(InterfaceError):
    """Exception for state store operations."""


class CheckExecutionError(InterfaceError):
    """Exception for health check execution."""


class ValidationError(InterfaceError):
    """Exception for validation operations."""


class ConfigUpdaterError(InterfaceError):
    """Exception for config updater operations."""


class PartialFailureError(GitOpsProviderError):
    """Exception for batch operations that partially succeeded.

    Attributes:
        successful_items: Count of successful operations
        failed_items: Count of failed operations
        errors: List of error messages for failed operations
        successful_keys: Keys/identifiers of successful operations
        failed_keys: Keys/identifiers of failed operations
    """

    def __init__(
        self,
        message: str,
        successful_items: int,
        failed_items: int,
        errors: list[str],
        successful_keys: list[str] | None = None,
        failed_keys: list[str] | None = None,
    ):
        """Initialize partial failure error.

        Args:
            message: Error message
            successful_items: Number of successful operations
            failed_items: Number of failed operations
            errors: List of error messages
            successful_keys: Optional list of identifiers for successful operations
            failed_keys: Optional list of identifiers for failed operations
        """
        super().__init__(message)
        self.successful_items = successful_items
        self.failed_items = failed_items
        self.errors = errors
        self.successful_keys = successful_keys or []
        self.failed_keys = failed_keys or []
