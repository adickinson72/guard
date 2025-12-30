"""Thanos service implementation."""

from typing import TYPE_CHECKING

from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, ServiceType, ValidationThresholds
from guard.interfaces.config_updater import ConfigUpdater
from guard.services.base import BaseService
from guard.services.thanos.config import (
    DEFAULT_THANOS_NAMESPACE,
    THANOS_METRIC_AGGREGATIONS,
)
from guard.utils.logging import get_logger
from guard.validation.validator_registry import ValidatorRegistry

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


class ThanosService(BaseService):
    """Thanos service implementation.

    Handles Thanos-specific upgrade operations including:
    - Health checks for query, store, and compactor components
    - Query latency validation
    - Store availability validation
    - Helm chart updates via Flux
    """

    @property
    def service_type(self) -> ServiceType:
        """Get the service type enum."""
        return ServiceType.THANOS

    @property
    def service_name(self) -> str:
        """Get human-readable service name."""
        return "thanos"

    @property
    def description(self) -> str:
        """Get service description."""
        return "Thanos - Long-term Prometheus storage and global query view"

    @property
    def default_namespace(self) -> str:
        """Get default Kubernetes namespace for Thanos."""
        return DEFAULT_THANOS_NAMESPACE

    def register_checks(self, registry: CheckRegistry) -> None:
        """Register Thanos-specific health checks.

        Args:
            registry: Check registry to register checks with
        """
        from guard.services.thanos.checks.compactor_health import ThanosCompactorHealthCheck
        from guard.services.thanos.checks.query_health import ThanosQueryHealthCheck
        from guard.services.thanos.checks.store_health import ThanosStoreHealthCheck

        registry.register(ThanosQueryHealthCheck())
        registry.register(ThanosStoreHealthCheck())
        registry.register(ThanosCompactorHealthCheck())

        logger.debug("thanos_checks_registered", count=3)

    def register_validators(self, registry: ValidatorRegistry) -> None:
        """Register Thanos-specific validators.

        Args:
            registry: Validator registry to register validators with
        """
        from guard.services.thanos.validators.query_latency import ThanosQueryLatencyValidator
        from guard.services.thanos.validators.store_availability import (
            ThanosStoreAvailabilityValidator,
        )

        registry.register(ThanosQueryLatencyValidator())
        registry.register(ThanosStoreAvailabilityValidator())

        logger.debug("thanos_validators_registered", count=2)

    def get_config_updater(self) -> ConfigUpdater:
        """Get Thanos-specific config updater.

        Returns:
            ConfigUpdater for Thanos Helm releases
        """
        from guard.services.thanos.updaters.helm_updater import ThanosHelmUpdater

        return ThanosHelmUpdater()

    async def validate_deployment(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate Thanos deployment after upgrade.

        Checks that all Thanos components are running and healthy.

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        from guard.services.thanos.operations import ThanosOperations

        logger.info("validating_thanos_deployment", cluster_id=cluster.cluster_id)
        return await ThanosOperations.validate_deployment(cluster, k8s_provider)

    async def perform_post_upgrade_operations(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform Thanos-specific post-upgrade operations.

        For Thanos, this typically involves:
        - Verifying store gateway has synced blocks
        - Checking compactor is not stuck
        - Validating query frontend cache

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating success/failure
        """
        from guard.services.thanos.operations import ThanosOperations

        logger.info("performing_thanos_post_upgrade_operations", cluster_id=cluster.cluster_id)
        return await ThanosOperations.perform_post_upgrade_checks(cluster, k8s_provider)

    def get_metric_aggregations(self) -> dict:
        """Get Thanos metric aggregation definitions.

        Returns:
            Dictionary of metric name to aggregation config
        """
        return THANOS_METRIC_AGGREGATIONS

    def get_validation_thresholds(self) -> ValidationThresholds:
        """Get Thanos-specific validation thresholds.

        Returns:
            ValidationThresholds instance configured for Thanos
        """
        # Return ValidationThresholds with Thanos-appropriate defaults
        # Thanos is more tolerant of latency increases during upgrades
        return ValidationThresholds(
            latency_p95_increase_percent=15.0,  # Thanos queries can be slower
            latency_p99_increase_percent=20.0,
            error_rate_max=0.001,
            error_rate_increase_max=0.0005,
            resource_increase_percent=30.0,  # Thanos stores may need more resources
        )
