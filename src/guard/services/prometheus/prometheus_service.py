"""Prometheus service implementation."""

from typing import TYPE_CHECKING, Any

from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, ServiceType, ValidationThresholds
from guard.interfaces.config_updater import ConfigUpdater
from guard.services.base import BaseService
from guard.services.prometheus.config import (
    DEFAULT_PROMETHEUS_NAMESPACE,
    PROMETHEUS_METRIC_AGGREGATIONS,
)
from guard.utils.logging import get_logger
from guard.validation.validator_registry import ValidatorRegistry

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


class PrometheusService(BaseService):
    """Prometheus service implementation.

    Handles Prometheus-specific upgrade operations including:
    - Health checks for server, alertmanager, and node-exporter
    - Query latency validation
    - Scrape target health validation
    - Helm chart updates via Flux
    """

    @property
    def service_type(self) -> ServiceType:
        """Get the service type enum."""
        return ServiceType.PROMETHEUS

    @property
    def service_name(self) -> str:
        """Get human-readable service name."""
        return "prometheus"

    @property
    def description(self) -> str:
        """Get service description."""
        return "Prometheus - Metrics collection and alerting"

    @property
    def default_namespace(self) -> str:
        """Get default Kubernetes namespace for Prometheus."""
        return DEFAULT_PROMETHEUS_NAMESPACE

    def register_checks(self, registry: CheckRegistry) -> None:
        """Register Prometheus-specific health checks.

        Args:
            registry: Check registry to register checks with
        """
        from guard.services.prometheus.checks.server_health import PrometheusServerHealthCheck
        from guard.services.prometheus.checks.storage_health import PrometheusStorageHealthCheck
        from guard.services.prometheus.checks.target_scraping import PrometheusTargetScrapingCheck

        registry.register(PrometheusServerHealthCheck())
        registry.register(PrometheusStorageHealthCheck())
        registry.register(PrometheusTargetScrapingCheck())

        logger.debug("prometheus_checks_registered", count=3)

    def register_validators(self, registry: ValidatorRegistry) -> None:
        """Register Prometheus-specific validators.

        Args:
            registry: Validator registry to register validators with
        """
        from guard.services.prometheus.validators.query_latency import (
            PrometheusQueryLatencyValidator,
        )
        from guard.services.prometheus.validators.scrape_health import (
            PrometheusScrapeHealthValidator,
        )

        registry.register(PrometheusQueryLatencyValidator())
        registry.register(PrometheusScrapeHealthValidator())

        logger.debug("prometheus_validators_registered", count=2)

    def get_config_updater(self) -> ConfigUpdater:
        """Get Prometheus-specific config updater.

        Returns:
            ConfigUpdater for Prometheus Helm releases
        """
        from guard.services.prometheus.updaters.helm_updater import PrometheusHelmUpdater

        return PrometheusHelmUpdater()

    async def validate_deployment(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate Prometheus deployment after upgrade.

        Checks that all Prometheus components are running and healthy.

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        from guard.services.prometheus.operations import PrometheusOperations

        logger.info("validating_prometheus_deployment", cluster_id=cluster.cluster_id)
        return await PrometheusOperations.validate_deployment(cluster, k8s_provider)

    async def perform_post_upgrade_operations(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform Prometheus-specific post-upgrade operations.

        For Prometheus, this typically involves:
        - Verifying TSDB is healthy
        - Checking scrape targets are being collected
        - Validating alertmanager connectivity

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating success/failure
        """
        from guard.services.prometheus.operations import PrometheusOperations

        logger.info("performing_prometheus_post_upgrade_operations", cluster_id=cluster.cluster_id)
        return await PrometheusOperations.perform_post_upgrade_checks(cluster, k8s_provider)

    def get_metric_aggregations(self) -> dict[str, Any]:
        """Get Prometheus metric aggregation definitions.

        Returns:
            Dictionary of metric name to aggregation config
        """
        return PROMETHEUS_METRIC_AGGREGATIONS

    def get_validation_thresholds(self) -> ValidationThresholds:
        """Get Prometheus-specific validation thresholds.

        Returns:
            ValidationThresholds instance configured for Prometheus
        """
        return ValidationThresholds(
            latency_p95_increase_percent=10.0,  # Standard latency tolerance
            latency_p99_increase_percent=15.0,
            error_rate_max=0.001,
            error_rate_increase_max=0.0005,
            resource_increase_percent=25.0,  # Prometheus may use more during compaction
        )
