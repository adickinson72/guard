"""Custom exceptions for GUARD."""


class IguError(Exception):
    """Base exception for all GUARD errors."""


class ConfigurationError(IguError):
    """Configuration-related errors."""


class PreCheckFailedError(IguError):
    """Pre-check validation failed."""


class ValidationFailedError(IguError):
    """Post-upgrade validation failed."""


class ClusterNotFoundError(IguError):
    """Cluster not found in registry."""


class GitOpsError(IguError):
    """GitLab/Git operation failed."""


class AWSError(IguError):
    """AWS operation failed."""


class DatadogError(IguError):
    """Datadog operation failed."""


class KubernetesError(IguError):
    """Kubernetes operation failed."""


class IstioError(IguError):
    """Istio operation failed."""


class RollbackError(IguError):
    """Rollback operation failed."""


class LockAcquisitionError(IguError):
    """Failed to acquire distributed lock."""
