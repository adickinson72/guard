"""Health check interface for pre-upgrade validation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from guard.core.models import CheckResult, ClusterConfig


@dataclass
class CheckContext:
    """Context passed to health checks containing dependencies."""

    cloud_provider: "CloudProvider"  # type: ignore
    kubernetes_provider: "KubernetesProvider"  # type: ignore
    metrics_provider: "MetricsProvider"  # type: ignore
    extra_context: dict[str, Any]


# Forward references for type checking
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from guard.interfaces.cloud_provider import CloudProvider
    from guard.interfaces.kubernetes_provider import KubernetesProvider
    from guard.interfaces.metrics_provider import MetricsProvider


class Check(ABC):
    """Abstract interface for health checks.

    This interface defines the contract for all health checks, both
    generic (Kubernetes, cloud) and service-specific (Istio, Promtail).

    Design Philosophy:
    - Single responsibility: each check validates one thing
    - Dependency injection: receives providers via context
    - Self-contained: can run independently
    - Failure isolation: one check failure doesn't prevent others
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the check name for logging/reporting.

        Returns:
            Human-readable check name
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Get a description of what this check validates.

        Returns:
            Description of the check's purpose
        """

    @abstractmethod
    async def execute(self, cluster: ClusterConfig, context: CheckContext) -> CheckResult:
        """Execute the health check.

        Args:
            cluster: Cluster configuration
            context: Check context with provider dependencies

        Returns:
            CheckResult indicating pass/fail and details

        Raises:
            CheckExecutionError: If check execution fails
        """

    @property
    def is_critical(self) -> bool:
        """Whether this is a critical check that blocks upgrades.

        Returns:
            True if check failure should block upgrade (default: True)
        """
        return True

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time for this check.

        Returns:
            Timeout in seconds (default: 60)
        """
        return 60
