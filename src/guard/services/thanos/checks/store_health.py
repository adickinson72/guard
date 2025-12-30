"""Thanos Store health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.thanos.config import DEFAULT_THANOS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ThanosStoreHealthCheck(Check):
    """Check Thanos Store gateway health.

    Validates that Thanos Store gateway pods are running and ready,
    which implies they have successfully synced blocks from object storage.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "thanos_store_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Thanos Store gateway pods are healthy and syncing blocks"

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
        """Execute Thanos Store health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_thanos_store_health", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_THANOS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Try standard label selector first
            pods = await k8s.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-store"
            )

            # Fallback to alternative label
            if not pods:
                pods = await k8s.get_pods(namespace=namespace, label_selector="app=thanos-store")

            if not pods:
                issues.append("No Thanos Store pods found")
            else:
                not_ready = [pod.name for pod in pods if not pod.ready]
                if not_ready:
                    issues.append(f"Store pods not ready: {', '.join(not_ready)}")
                else:
                    logger.info(
                        "thanos_store_pods_healthy",
                        cluster_id=cluster.cluster_id,
                        pod_count=len(pods),
                    )

        except Exception as e:
            issues.append(f"Failed to check Store pods: {e!s}")
            logger.error(
                "thanos_store_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Thanos Store pods are healthy"
            if passed
            else f"Thanos Store health check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues},
            timestamp=datetime.utcnow(),
        )
