"""Prometheus Target Scraping health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.prometheus.config import DEFAULT_PROMETHEUS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusTargetScrapingCheck(Check):
    """Check Prometheus target scraping health.

    Validates that Prometheus is successfully scraping targets.
    This is inferred from node-exporter pods being present and healthy,
    as they are commonly scraped targets.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "prometheus_target_scraping"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Prometheus targets are being scraped (via node-exporter health)"

    @property
    def is_critical(self) -> bool:
        """Whether this check is critical."""
        return False  # Target scraping can recover

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time."""
        return 60

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute Prometheus target scraping check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_prometheus_target_scraping", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_PROMETHEUS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Check node-exporter pods as proxy for scraping health
            pods = await k8s.get_pods(
                namespace=namespace,
                label_selector="app.kubernetes.io/name=prometheus-node-exporter",
            )

            # Fallback to alternative label
            if not pods:
                pods = await k8s.get_pods(namespace=namespace, label_selector="app=node-exporter")

            if not pods:
                # Node-exporter is optional
                logger.info(
                    "prometheus_node_exporter_not_deployed",
                    cluster_id=cluster.cluster_id,
                    message="Node-exporter is optional",
                )
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message="Node-exporter not deployed (scraping check skipped)",
                    metrics={"issues": [], "deployed": False},
                    timestamp=datetime.utcnow(),
                )

            not_ready = [pod.name for pod in pods if not pod.ready]
            if not_ready:
                issues.append(f"Node-exporter pods not ready: {', '.join(not_ready)}")
            else:
                logger.info(
                    "prometheus_node_exporter_pods_healthy",
                    cluster_id=cluster.cluster_id,
                    pod_count=len(pods),
                )

        except Exception as e:
            issues.append(f"Failed to check scraping targets: {e!s}")
            logger.error(
                "prometheus_target_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Prometheus targets are healthy"
            if passed
            else f"Prometheus target scraping check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues, "deployed": True},
            timestamp=datetime.utcnow(),
        )
