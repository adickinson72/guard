"""Istioctl analyze health check."""

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioCtlAnalyzeCheck(Check):
    """Check Istio configuration using istioctl analyze.

    Runs istioctl analyze to validate Istio configuration
    and detect potential issues.
    """

    @property
    def name(self) -> str:
        """Get check name."""
        return "istioctl_analyze"

    @property
    def description(self) -> str:
        """Get check description."""
        return "Validates Istio configuration using istioctl analyze"

    async def execute(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> CheckResult:
        """Execute istioctl analyze check.

        Args:
            cluster: Cluster configuration
            context: Check context with providers

        Returns:
            CheckResult indicating pass/fail
        """
        logger.info("running_istioctl_analyze", cluster_id=cluster.cluster_id)

        try:
            # Get or create istioctl wrapper
            from guard.clients.istioctl import IstioctlWrapper

            istioctl = context.extra_context.get("istioctl")
            if not istioctl:
                # Create wrapper with cluster context
                # In a real setup, this would use the kubeconfig for the cluster
                istioctl = IstioctlWrapper(
                    kubeconfig_path=context.extra_context.get("kubeconfig_path"),
                    context=cluster.cluster_id,
                )

            # Run istioctl analyze across all namespaces
            no_issues, output = istioctl.analyze(namespace=None)

            if no_issues:
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    message="Istioctl analyze completed with no errors",
                    metrics={"issues_found": 0},
                )
            else:
                # Parse output to count issues
                # Output typically contains lines like:
                # "Error [IST0101] (Deployment foo/bar) Referenced service not found"
                # "Warning [IST0118] (Pod foo/bar) Port 443 is exposed"
                lines = output.strip().split("\n")
                error_count = sum(1 for line in lines if "Error" in line)
                warning_count = sum(1 for line in lines if "Warning" in line)

                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    message=f"Istioctl analyze found {error_count} errors and {warning_count} warnings",
                    metrics={
                        "issues_found": error_count + warning_count,
                        "errors": error_count,
                        "warnings": warning_count,
                    },
                    details={"output": output},
                )

        except Exception as e:
            logger.error(
                "istioctl_analyze_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )

            return CheckResult(
                check_name=self.name,
                passed=False,
                message=f"Istioctl analyze failed: {e}",
                metrics={},
            )

    @property
    def timeout_seconds(self) -> int:
        """Get timeout for this check."""
        return 120  # istioctl can take a while
