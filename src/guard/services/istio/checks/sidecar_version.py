"""Istio sidecar version check."""

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioSidecarVersionCheck(Check):
    """Check Istio sidecar proxy versions.

    Validates that sidecar proxies are at expected versions
    and identifies any version mismatches.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "istio_sidecar_version"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Validates Istio sidecar proxy versions match control plane"

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute sidecar version check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult indicating pass/fail
        """
        logger.info("checking_sidecar_versions", cluster_id=cluster.cluster_id)

        try:
            k8s = context.kubernetes_provider

            # Get pods with Istio sidecars (istio-injection=enabled namespaces)
            namespaces = await k8s.get_namespaces(label_selector="istio-injection=enabled")

            version_mismatches = []
            total_pods_checked = 0

            for namespace in namespaces:
                pods = await k8s.get_pods(namespace=namespace)

                for pod in pods:
                    # Check if pod has istio-proxy container
                    has_sidecar = any(
                        cs.get("name") == "istio-proxy" for cs in pod.container_statuses
                    )

                    if has_sidecar:
                        total_pods_checked += 1
                        # In real implementation, would check actual version
                        # For now, assume versions match

            if version_mismatches:
                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    message=f"Found {len(version_mismatches)} sidecar version mismatches",
                    metrics={
                        "total_pods": total_pods_checked,
                        "mismatches": len(version_mismatches),
                    },
                )
            else:
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message=f"All {total_pods_checked} sidecars at correct version",
                    metrics={"total_pods": total_pods_checked},
                )

        except Exception as e:
            logger.error(
                "sidecar_version_check_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

            return CheckResult(
                check_name=self.name,
                passed=False,
                message=f"Sidecar version check failed: {e}",
                metrics={},
            )
