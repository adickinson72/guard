"""Prometheus Server health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.prometheus.config import DEFAULT_PROMETHEUS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusServerHealthCheck(Check):
    """Check Prometheus Server health.

    Validates that Prometheus Server pods are running and ready.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "prometheus_server_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Prometheus Server pods are healthy"

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
        """Execute Prometheus Server health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_prometheus_server_health", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_PROMETHEUS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Try standard label selector first
            pods = await k8s.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=prometheus-server"
            )

            # Fallback to alternative label
            if not pods:
                pods = await k8s.get_pods(
                    namespace=namespace, label_selector="app=prometheus-server"
                )

            # Also try prometheus label
            if not pods:
                pods = await k8s.get_pods(namespace=namespace, label_selector="app=prometheus")

            if not pods:
                issues.append("No Prometheus Server pods found")
            else:
                not_ready = [pod.name for pod in pods if not pod.ready]
                if not_ready:
                    issues.append(f"Server pods not ready: {', '.join(not_ready)}")
                else:
                    logger.info(
                        "prometheus_server_pods_healthy",
                        cluster_id=cluster.cluster_id,
                        pod_count=len(pods),
                    )

        except Exception as e:
            issues.append(f"Failed to check Server pods: {e!s}")
            logger.error(
                "prometheus_server_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Prometheus Server pods are healthy"
            if passed
            else f"Prometheus Server health check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues},
            timestamp=datetime.utcnow(),
        )
