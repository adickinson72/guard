"""Custom exceptions for GUARD."""


class GuardError(Exception):
    """Base exception for all GUARD errors."""


class ConfigurationError(GuardError):
    """Configuration-related errors."""


class PreCheckFailedError(GuardError):
    """Pre-check validation failed."""


class ValidationFailedError(GuardError):
    """Post-upgrade validation failed."""


class ClusterNotFoundError(GuardError):
    """Cluster not found in registry."""


class GitOpsError(GuardError):
    """GitLab/Git operation failed."""


class AWSError(GuardError):
    """AWS operation failed."""


class DatadogError(GuardError):
    """Datadog operation failed."""


class KubernetesError(GuardError):
    """Kubernetes operation failed."""


class IstioError(GuardError):
    """Istio operation failed."""


class RollbackError(GuardError):
    """Rollback operation failed."""


class LockAcquisitionError(GuardError):
    """Failed to acquire distributed lock."""
