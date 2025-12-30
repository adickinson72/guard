"""Istio service facade - single entry point for all Istio operations."""

from typing import TYPE_CHECKING

from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, MetricAggregation, ServiceType
from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
from guard.interfaces.config_updater import ConfigUpdater
from guard.services.base import BaseService
from guard.services.istio.checks.istioctl_analyze import IstioCtlAnalyzeCheck
from guard.services.istio.checks.sidecar_version import IstioSidecarVersionCheck
from guard.services.istio.validators.error_rate import IstioErrorRateValidator
from guard.services.istio.validators.latency import IstioLatencyValidator
from guard.utils.logging import get_logger
from guard.validation.validator_registry import ValidatorRegistry

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig, ValidationThresholds
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


# Istio-specific metric aggregations
ISTIO_METRIC_AGGREGATIONS: dict[str, MetricAggregation] = {
    # Latency metrics - use percentiles
    "istio.request.duration.p95": MetricAggregation.P95,
    "istio.request.duration.p99": MetricAggregation.P99,
    # Error rates - use max to catch spikes
    "istio.request.error_rate": MetricAggregation.MAX,
    # Request counts - use sum for totals
    "istio.request.count": MetricAggregation.SUM,
    # Resource metrics - use avg
    "istiod.cpu": MetricAggregation.AVG,
    "istiod.memory": MetricAggregation.AVG,
    "istiod.cpu_usage": MetricAggregation.AVG,
    "istiod.mem_usage": MetricAggregation.AVG,
    "gateway.cpu": MetricAggregation.AVG,
    "gateway.memory": MetricAggregation.AVG,
    "gateway.cpu_usage": MetricAggregation.AVG,
    "gateway.mem_usage": MetricAggregation.AVG,
    # Pilot metrics - use sum for counts, max for rates
    "pilot_total_xds_rejects": MetricAggregation.SUM,
    "pilot.xds.rejects": MetricAggregation.SUM,
    "pilot_xds_push_errors": MetricAggregation.MAX,
    "pilot.xds.push_errors": MetricAggregation.MAX,
}


class IstioService(BaseService):
    """Facade for all Istio-specific operations.

    This facade provides a single interface for:
    - Registering Istio-specific health checks
    - Registering Istio-specific validators
    - Getting Istio config updater
    - Validating Istio deployments
    - Performing post-upgrade operations (sidecar restarts)
    """

    def __init__(self) -> None:
        """Initialize Istio service."""
        logger.debug("istio_service_initialized")

    @property
    def service_type(self) -> ServiceType:
        """Get the service type enum."""
        return ServiceType.ISTIO

    @property
    def service_name(self) -> str:
        """Get service name."""
        return "istio"

    @property
    def description(self) -> str:
        """Get service description."""
        return "Istio service mesh upgrade management"

    @property
    def default_namespace(self) -> str:
        """Get default Kubernetes namespace for Istio."""
        return "istio-system"

    def register_checks(self, registry: CheckRegistry) -> None:
        """Register all Istio health checks.

        Args:
            registry: Check registry to register with
        """
        logger.info("registering_istio_checks")

        # Register Istio-specific checks
        registry.register(IstioCtlAnalyzeCheck())
        registry.register(IstioSidecarVersionCheck())

        logger.info("istio_checks_registered", count=2)

    def register_validators(self, registry: ValidatorRegistry) -> None:
        """Register all Istio validators.

        Args:
            registry: Validator registry to register with
        """
        logger.info("registering_istio_validators")

        # Register Istio-specific validators
        registry.register(IstioLatencyValidator())
        registry.register(IstioErrorRateValidator())

        logger.info("istio_validators_registered", count=2)

    def get_config_updater(self) -> ConfigUpdater:
        """Get Istio config updater.

        Returns:
            ConfigUpdater for Istio HelmRelease files
        """
        return IstioHelmUpdater()

    async def validate_deployment(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate Istio deployment after upgrade.

        Performs comprehensive Istio health checks including:
        - istiod pods ready and running
        - Gateway pods ready and running
        - istioctl analyze for configuration errors
        - istioctl proxy-status for data plane connectivity

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating deployment health
        """
        # Delegate to IstioOperations
        from guard.services.istio.operations import IstioOperations

        return await IstioOperations.validate_deployment(cluster, k8s_provider)

    async def perform_post_upgrade_operations(
        self,
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform Istio post-upgrade operations.

        For Istio, this restarts all pods with sidecars to ensure
        sidecar proxy versions match the new control plane version.

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating operation success/failure
        """
        # Delegate to IstioOperations
        from guard.services.istio.operations import IstioOperations

        logger.info("performing_post_upgrade_operations", cluster_id=cluster.cluster_id)
        return await IstioOperations.restart_pods_with_sidecars(k8s_provider)

    def get_metric_aggregations(self) -> dict[str, MetricAggregation]:
        """Get Istio-specific metric aggregation mappings.

        Returns:
            Dict mapping Istio metric names to aggregation types
        """
        return ISTIO_METRIC_AGGREGATIONS

    def get_validation_thresholds(self) -> "ValidationThresholds":
        """Get Istio-specific validation thresholds.

        Returns:
            ValidationThresholds with Istio-specific defaults
        """
        from guard.core.models import ValidationThresholds

        # Use default thresholds which include Istio-specific fields
        return ValidationThresholds()
