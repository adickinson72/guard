"""Thanos Query health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.thanos.config import DEFAULT_THANOS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ThanosQueryHealthCheck(Check):
    """Check Thanos Query component health.

    Validates that Thanos Query pods are running and ready,
    which implies they can reach and aggregate from stores.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "thanos_query_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Thanos Query pods are healthy and can reach stores"

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
        """Execute Thanos Query health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_thanos_query_health", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_THANOS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Try standard label selector first
            pods = await k8s.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-query"
            )

            # Fallback to alternative label
            if not pods:
                pods = await k8s.get_pods(namespace=namespace, label_selector="app=thanos-query")

            if not pods:
                issues.append("No Thanos Query pods found")
            else:
                not_ready = [pod.name for pod in pods if not pod.ready]
                if not_ready:
                    issues.append(f"Query pods not ready: {', '.join(not_ready)}")
                else:
                    logger.info(
                        "thanos_query_pods_healthy",
                        cluster_id=cluster.cluster_id,
                        pod_count=len(pods),
                    )

        except Exception as e:
            issues.append(f"Failed to check Query pods: {e!s}")
            logger.error(
                "thanos_query_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Thanos Query pods are healthy"
            if passed
            else f"Thanos Query health check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues},
            timestamp=datetime.utcnow(),
        )
