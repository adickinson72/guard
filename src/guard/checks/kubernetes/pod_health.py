"""Pod health check for specific namespaces."""

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PodHealthCheck(Check):
    """Check pod health in specified namespaces.

    Validates that pods in critical namespaces are running and ready.
    """

    def __init__(self, namespaces: list[str] | None = None):
        """Initialize pod health check.

        Args:
            namespaces: List of namespaces to check (default: kube-system)
        """
        self.namespaces = namespaces or ["kube-system"]

    @property
    def name(self) -> str:
        """Get check name."""
        return "pod_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return f"Validates pods are healthy in namespaces: {', '.join(self.namespaces)}"

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute pod health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult indicating pass/fail
        """
        logger.info(
            "checking_pod_health",
            cluster_id=cluster.cluster_id,
            namespaces=self.namespaces,
        )

        try:
            k8s = context.kubernetes_provider
            total_unready = []

            for namespace in self.namespaces:
                all_ready, unready_pods = await k8s.check_pods_ready(namespace)

                if not all_ready:
                    total_unready.extend([f"{namespace}/{pod}" for pod in unready_pods])

            if not total_unready:
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message=f"All pods ready in {', '.join(self.namespaces)}",
                    metrics={"unready_count": 0},
                )
            else:
                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    message=f"Not all pods ready: {', '.join(total_unready[:5])}...",
                    metrics={
                        "unready_count": len(total_unready),
                        "unready_pods": total_unready,
                    },
                )

        except Exception as e:
            logger.error(
                "pod_health_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

            return CheckResult(
                check_name=self.name,
                passed=False,
                message=f"Pod health check failed: {e}",
                metrics={},
            )
