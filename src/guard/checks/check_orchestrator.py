"""Check orchestrator for running health checks."""

import asyncio

from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import CheckContext
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class CheckOrchestrator:
    """Orchestrates execution of health checks.

    This orchestrator coordinates check execution without knowing
    the specifics of each check. It handles:
    - Check execution with timeouts
    - Dependency injection via CheckContext
    - Failure isolation
    - Result aggregation
    """

    def __init__(
        self,
        registry: CheckRegistry,
        fail_fast: bool = True,
        max_concurrent: int = 5,
    ):
        """Initialize check orchestrator.

        Args:
            registry: Check registry containing registered checks
            fail_fast: Stop on first check failure (default: True)
            max_concurrent: Maximum concurrent check executions
        """
        self.registry = registry
        self.fail_fast = fail_fast
        self.max_concurrent = max_concurrent
        logger.debug(
            "check_orchestrator_initialized",
            fail_fast=fail_fast,
            max_concurrent=max_concurrent,
        )

    async def run_checks(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> list[CheckResult]:
        """Run all registered checks for a cluster.

        Args:
            cluster: Cluster configuration
            context: Check context with provider dependencies

        Returns:
            List of check results

        Raises:
            Exception: If check execution fails critically
        """
        logger.info("running_checks", cluster_id=cluster.cluster_id)

        checks = self.registry.get_checks_for_cluster(cluster)
        results = []

        for check in checks:
            logger.debug("executing_check", check_name=check.name)

            try:
                # Execute check with timeout
                result = await asyncio.wait_for(
                    check.execute(cluster, context),
                    timeout=check.timeout_seconds,
                )
                results.append(result)

                logger.info(
                    "check_completed",
                    check_name=check.name,
                    passed=result.passed,
                )

                # Fail fast if enabled and check failed
                if self.fail_fast and not result.passed and check.is_critical:
                    logger.warning(
                        "check_failed_stopping",
                        check_name=check.name,
                        message=result.message,
                    )
                    break

            except TimeoutError:
                logger.error(
                    "check_timeout",
                    check_name=check.name,
                    timeout=check.timeout_seconds,
                )

                # Create failure result for timeout
                result = CheckResult(
                    check_name=check.name,
                    passed=False,
                    message=f"Check timed out after {check.timeout_seconds} seconds",
                    metrics={},
                )
                results.append(result)

                if self.fail_fast and check.is_critical:
                    break

            except Exception as e:
                logger.error(
                    "check_execution_failed",
                    check_name=check.name,
                    error=str(e),
                )

                # Create failure result for exception
                result = CheckResult(
                    check_name=check.name,
                    passed=False,
                    message=f"Check failed with error: {e}",
                    metrics={},
                )
                results.append(result)

                if self.fail_fast and check.is_critical:
                    break

        all_passed = all(r.passed for r in results)
        logger.info(
            "checks_completed",
            cluster_id=cluster.cluster_id,
            total=len(results),
            passed=sum(1 for r in results if r.passed),
            all_passed=all_passed,
        )

        return results

    async def run_specific_checks(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
        check_names: list[str],
    ) -> list[CheckResult]:
        """Run specific named checks.

        Args:
            cluster: Cluster configuration
            context: Check context
            check_names: Names of checks to run

        Returns:
            List of check results
        """
        logger.info(
            "running_specific_checks",
            cluster_id=cluster.cluster_id,
            check_names=check_names,
        )

        results = []
        for check_name in check_names:
            check = self.registry.get_check(check_name)
            if not check:
                logger.warning("check_not_found", check_name=check_name)
                continue

            try:
                result = await asyncio.wait_for(
                    check.execute(cluster, context),
                    timeout=check.timeout_seconds,
                )
                results.append(result)

            except Exception as e:
                logger.error("check_execution_failed", check_name=check_name, error=str(e))
                result = CheckResult(
                    check_name=check_name,
                    passed=False,
                    message=f"Check failed: {e}",
                    metrics={},
                )
                results.append(result)

        return results

    async def run_critical_checks_only(
        self,
        cluster: ClusterConfig,
        context: CheckContext,
    ) -> list[CheckResult]:
        """Run only critical checks.

        Args:
            cluster: Cluster configuration
            context: Check context

        Returns:
            List of check results from critical checks
        """
        logger.info("running_critical_checks_only", cluster_id=cluster.cluster_id)

        critical_checks = self.registry.get_critical_checks()
        results = []

        for check in critical_checks:
            try:
                result = await asyncio.wait_for(
                    check.execute(cluster, context),
                    timeout=check.timeout_seconds,
                )
                results.append(result)

                if self.fail_fast and not result.passed:
                    break

            except Exception as e:
                logger.error("check_execution_failed", check_name=check.name, error=str(e))
                result = CheckResult(
                    check_name=check.name,
                    passed=False,
                    message=f"Check failed: {e}",
                    metrics={},
                )
                results.append(result)

                if self.fail_fast:
                    break

        return results
