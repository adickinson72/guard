"""Istio sidecar version check."""

import re

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

    def _extract_version_from_image(self, image: str) -> str | None:
        """Extract version from container image tag.

        Args:
            image: Container image (e.g., "istio/proxyv2:1.20.0")

        Returns:
            Version string or None if not found
        """
        # Match patterns like:
        # - istio/proxyv2:1.20.0
        # - docker.io/istio/proxyv2:1.20.0-distroless
        # - gcr.io/istio-release/proxyv2:1.20.0
        match = re.search(r":(\d+\.\d+\.\d+)", image)
        if match:
            return match.group(1)

        logger.debug("version_extraction_failed", image=image)
        return None

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
            expected_version = cluster.current_istio_version

            for namespace in namespaces:
                pods = await k8s.get_pods(namespace=namespace)

                for pod in pods:
                    # Find istio-proxy container in container statuses
                    proxy_image = None
                    for container_status in pod.container_statuses:
                        if container_status.get("name") == "istio-proxy":
                            proxy_image = container_status.get("image")
                            break

                    if proxy_image:
                        total_pods_checked += 1

                        # Extract version from container image
                        actual_version = self._extract_version_from_image(proxy_image)

                        # Compare versions
                        if actual_version and actual_version != expected_version:
                            version_mismatches.append(
                                {
                                    "pod": f"{namespace}/{pod.name}",
                                    "expected": expected_version,
                                    "actual": actual_version,
                                    "image": proxy_image,
                                }
                            )
                            logger.warning(
                                "sidecar_version_mismatch",
                                pod=f"{namespace}/{pod.name}",
                                expected=expected_version,
                                actual=actual_version,
                            )

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
