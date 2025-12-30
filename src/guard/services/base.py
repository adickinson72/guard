"""Base service interface for all service implementations."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from guard.core.models import CheckResult, MetricAggregation, ServiceType

if TYPE_CHECKING:
    from guard.checks.check_registry import CheckRegistry
    from guard.core.models import ClusterConfig, ValidationThresholds
    from guard.interfaces.config_updater import ConfigUpdater
    from guard.interfaces.kubernetes_provider import KubernetesProvider
    from guard.validation.validator_registry import ValidatorRegistry


class BaseService(ABC):
    """Abstract base class for service-specific operations.

    Each service (Istio, Thanos, Prometheus) implements this interface
    to provide its specific checks, validators, updaters, and operations.

    Design Philosophy:
    - Single responsibility: each service owns its domain logic
    - Dependency injection: registries passed to registration methods
    - Self-contained: service modules are isolated
    - Extensible: new services implement this interface
    """

    @property
    @abstractmethod
    def service_type(self) -> ServiceType:
        """Get the service type enum.

        Returns:
            ServiceType enum value
        """

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Get human-readable service name.

        Returns:
            Service name for display/logging
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Get service description.

        Returns:
            Description of what this service manages
        """

    @property
    @abstractmethod
    def default_namespace(self) -> str:
        """Get default Kubernetes namespace for this service.

        Returns:
            Namespace where service components run (e.g., istio-system)
        """

    @abstractmethod
    def register_checks(self, registry: "CheckRegistry") -> None:
        """Register all service-specific health checks.

        Args:
            registry: Check registry to register with
        """

    @abstractmethod
    def register_validators(self, registry: "ValidatorRegistry") -> None:
        """Register all service-specific validators.

        Args:
            registry: Validator registry to register with
        """

    @abstractmethod
    def get_config_updater(self) -> "ConfigUpdater":
        """Get the config updater for this service.

        Returns:
            ConfigUpdater implementation for this service's Flux configs
        """

    @abstractmethod
    async def validate_deployment(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate service deployment after upgrade.

        Service-specific validation logic:
        - Istio: checks istiod pods, gateway pods, runs istioctl analyze
        - Thanos: checks store/query/compactor pods
        - Prometheus: checks server pods, target scraping

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating deployment health
        """

    @abstractmethod
    async def perform_post_upgrade_operations(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform any post-upgrade operations specific to this service.

        Examples:
        - Istio: restart pods with sidecars to pick up new proxy version
        - Thanos: verify store sync across components
        - Prometheus: verify target scraping resumed

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating operation success/failure
        """

    def get_metric_aggregations(self) -> dict[str, MetricAggregation]:
        """Get service-specific metric aggregation mappings.

        Override in subclass to provide metrics for this service.

        Returns:
            Dict mapping metric names to aggregation types
        """
        return {}

    def get_validation_thresholds(self) -> "ValidationThresholds":
        """Get service-specific validation thresholds.

        Override in subclass to provide custom thresholds.

        Returns:
            ValidationThresholds for this service
        """
        from guard.core.models import ValidationThresholds

        return ValidationThresholds()
