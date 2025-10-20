"""Pre-check engine for validating cluster health before upgrades."""

from guard.core.models import CheckResult, ClusterConfig
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class HealthCheck:
    """Base class for health checks."""

    def run(self, cluster: ClusterConfig) -> CheckResult:
        """Run the health check.

        Args:
            cluster: Cluster configuration

        Returns:
            CheckResult with pass/fail status
        """
        raise NotImplementedError("Subclasses must implement run()")


class PreCheckEngine:
    """Engine for orchestrating pre-upgrade health checks."""

    def __init__(self, checks: list[HealthCheck]):
        """Initialize pre-check engine.

        Args:
            checks: List of health check instances
        """
        self.checks = checks
        logger.debug("pre_check_engine_initialized", check_count=len(checks))

    def run_all_checks(self, cluster: ClusterConfig) -> list[CheckResult]:
        """Run all health checks for a cluster.

        Args:
            cluster: Cluster configuration

        Returns:
            List of check results (stops on first failure)
        """
        logger.info("running_pre_checks", cluster_id=cluster.cluster_id)

        results = []
        for check in self.checks:
            logger.debug("running_check", check=check.__class__.__name__)

            result = check.run(cluster)
            results.append(result)

            if not result.passed:
                logger.warning(
                    "check_failed",
                    check=check.__class__.__name__,
                    message=result.message,
                )
                break

        all_passed = all(r.passed for r in results)
        logger.info(
            "pre_checks_completed",
            cluster_id=cluster.cluster_id,
            all_passed=all_passed,
            total_checks=len(results),
        )

        return results
