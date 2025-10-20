"""Node readiness health check."""

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class NodeReadinessCheck(Check):
    """Check that all nodes are in Ready state.

    Validates that all cluster nodes are ready to accept workloads.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "node_readiness"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Validates all cluster nodes are in Ready state"

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute node readiness check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult indicating pass/fail
        """
        logger.info("checking_node_readiness", cluster_id=cluster.cluster_id)

        try:
            k8s = context.kubernetes_provider

            # Check node readiness
            all_ready, unready_nodes = await k8s.check_nodes_ready()

            if all_ready:
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message="All nodes are ready",
                    metrics={"unready_count": 0},
                )
            else:
                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    message=f"Not all nodes ready: {', '.join(unready_nodes)}",
                    metrics={
                        "unready_count": len(unready_nodes),
                        "unready_nodes": unready_nodes,
                    },
                )

        except Exception as e:
            logger.error(
                "node_readiness_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

            return CheckResult(
                check_name=self.name,
                passed=False,
                message=f"Node readiness check failed: {e}",
                metrics={},
            )
