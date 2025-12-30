"""Prometheus Storage health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.prometheus.config import DEFAULT_PROMETHEUS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusStorageHealthCheck(Check):
    """Check Prometheus TSDB storage health.

    Validates that Prometheus Server pods are healthy, which implies
    the TSDB storage is functioning correctly.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "prometheus_storage_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Prometheus TSDB storage is healthy"

    @property
    def is_critical(self) -> bool:
        """Whether this check is critical."""
        return True

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time."""
        return 60

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute Prometheus storage health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_prometheus_storage_health", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_PROMETHEUS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Check server pods - if running, TSDB is healthy
            pods = await k8s.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=prometheus-server"
            )

            if not pods:
                pods = await k8s.get_pods(
                    namespace=namespace, label_selector="app=prometheus-server"
                )

            if not pods:
                pods = await k8s.get_pods(namespace=namespace, label_selector="app=prometheus")

            if not pods:
                issues.append("No Prometheus Server pods found for storage check")
            else:
                # Check for CrashLoopBackOff or other storage-related issues
                for pod in pods:
                    if not pod.ready:
                        # Get pod phase from container statuses if available
                        issues.append(f"Server pod {pod.name} not ready - possible TSDB issue")

                if not issues:
                    logger.info(
                        "prometheus_storage_healthy",
                        cluster_id=cluster.cluster_id,
                        pod_count=len(pods),
                    )

        except Exception as e:
            issues.append(f"Failed to check storage health: {e!s}")
            logger.error(
                "prometheus_storage_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Prometheus TSDB storage is healthy"
            if passed
            else f"Prometheus storage health check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues},
            timestamp=datetime.utcnow(),
        )
