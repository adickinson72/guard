"""Thanos Compactor health check."""

from datetime import datetime

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.services.thanos.config import DEFAULT_THANOS_NAMESPACE
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ThanosCompactorHealthCheck(Check):
    """Check Thanos Compactor health.

    Validates that Thanos Compactor pods are running and ready.
    Note: Compactor is optional in some deployments.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "thanos_compactor_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Verify Thanos Compactor pods are healthy (optional component)"

    @property
    def is_critical(self) -> bool:
        """Whether this check is critical - Compactor is optional."""
        return False

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time."""
        return 60

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute Thanos Compactor health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult with pass/fail status
        """
        logger.info("checking_thanos_compactor_health", cluster_id=cluster.cluster_id)

        namespace = DEFAULT_THANOS_NAMESPACE
        issues: list[str] = []
        k8s = context.kubernetes_provider

        try:
            # Try standard label selector first
            pods = await k8s.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-compactor"
            )

            # Fallback to alternative label
            if not pods:
                pods = await k8s.get_pods(
                    namespace=namespace, label_selector="app=thanos-compactor"
                )

            if not pods:
                # Compactor is optional - not having it is not a failure
                logger.info(
                    "thanos_compactor_not_deployed",
                    cluster_id=cluster.cluster_id,
                    message="Compactor is optional",
                )
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message="Thanos Compactor not deployed (optional component)",
                    metrics={"issues": [], "deployed": False},
                    timestamp=datetime.utcnow(),
                )

            not_ready = [pod.name for pod in pods if not pod.ready]
            if not_ready:
                issues.append(f"Compactor pods not ready: {', '.join(not_ready)}")
            else:
                logger.info(
                    "thanos_compactor_pods_healthy",
                    cluster_id=cluster.cluster_id,
                    pod_count=len(pods),
                )

        except Exception as e:
            issues.append(f"Failed to check Compactor pods: {e!s}")
            logger.error(
                "thanos_compactor_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

        passed = len(issues) == 0
        message = (
            "Thanos Compactor pods are healthy"
            if passed
            else f"Thanos Compactor health check failed: {'; '.join(issues)}"
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            message=message,
            metrics={"issues": issues, "deployed": True},
            timestamp=datetime.utcnow(),
        )
