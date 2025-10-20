"""Control plane health check."""

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ControlPlaneHealthCheck(Check):
    """Check Kubernetes control plane health.

    Validates that the Kubernetes API server is responsive
    and the cluster is accessible.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "control_plane_health"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Validates Kubernetes control plane is healthy and accessible"

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute control plane health check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult indicating pass/fail
        """
        logger.info("checking_control_plane", cluster_id=cluster.cluster_id)

        try:
            k8s = context.kubernetes_provider

            # Try to list nodes as a health check
            nodes = await k8s.get_nodes()

            if not nodes:
                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    message="Control plane accessible but no nodes found",
                    metrics={"node_count": 0},
                )

            # Control plane is healthy if we can list nodes
            return CheckResult(
                check_name=self.name,
                passed=True,
                message=f"Control plane healthy, {len(nodes)} nodes found",
                metrics={"node_count": len(nodes)},
            )

        except Exception as e:
            logger.error(
                "control_plane_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

            return CheckResult(
                check_name=self.name,
                passed=False,
                message=f"Control plane unhealthy: {e}",
                metrics={},
            )
