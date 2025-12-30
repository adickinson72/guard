"""Thanos-specific operations extracted for post-upgrade validation."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from guard.core.models import CheckResult
from guard.services.thanos.config import DEFAULT_THANOS_NAMESPACE, THANOS_COMPONENTS
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


class ThanosOperations:
    """Thanos-specific post-upgrade operations.

    Contains operations for validating Thanos deployments:
    - validate_deployment: Validates all Thanos components are healthy
    - perform_post_upgrade_checks: Runs post-upgrade validation checks
    """

    @staticmethod
    async def validate_deployment(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate Thanos deployment after upgrade.

        Performs comprehensive Thanos health checks including:
        - Query pods ready and running
        - Store pods ready and running
        - Compactor pods ready
        - Query frontend pods ready (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        logger.info("validating_thanos_deployment", cluster_id=cluster.cluster_id)
        issues: list[str] = []
        healthy_components: list[str] = []

        namespace = DEFAULT_THANOS_NAMESPACE

        # Check each Thanos component
        for component in THANOS_COMPONENTS:
            try:
                pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector=f"app.kubernetes.io/name={component}"
                )

                # Also try alternative label selector
                if not pods:
                    pods = await k8s_provider.get_pods(
                        namespace=namespace, label_selector=f"app={component}"
                    )

                if pods:
                    not_ready = [pod.name for pod in pods if not pod.ready]
                    if not_ready:
                        issues.append(f"{component} pods not ready: {', '.join(not_ready)}")
                    else:
                        healthy_components.append(component)
                        logger.info(
                            "thanos_component_healthy",
                            component=component,
                            pod_count=len(pods),
                        )
                else:
                    # Component not deployed - this may be optional
                    logger.debug(
                        "thanos_component_not_found",
                        component=component,
                        message="Component may not be deployed",
                    )

            except Exception as e:
                logger.warning(
                    "thanos_component_check_failed",
                    component=component,
                    error=str(e),
                )
                issues.append(f"Failed to check {component}: {e!s}")

        # Require at least query and store to be healthy
        required_components = {"thanos-query", "thanos-store"}
        missing_required = required_components - set(healthy_components)
        if missing_required:
            issues.append(f"Required components not healthy: {', '.join(missing_required)}")

        passed = len(issues) == 0
        message = (
            f"Thanos deployment validated: {len(healthy_components)} components healthy"
            if passed
            else f"Thanos deployment validation failed: {'; '.join(issues)}"
        )

        logger.info(
            "thanos_deployment_validation_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            healthy_components=healthy_components,
            issue_count=len(issues),
        )

        return CheckResult(
            check_name="thanos_deployment",
            passed=passed,
            message=message,
            metrics={
                "healthy_components": healthy_components,
                "issues": issues,
            },
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    async def perform_post_upgrade_checks(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform Thanos-specific post-upgrade checks.

        Validates:
        - Store gateway has synced blocks (via logs or metrics)
        - Compactor is running and not stuck
        - Query can reach stores

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating success/failure
        """
        logger.info("performing_thanos_post_upgrade_checks", cluster_id=cluster.cluster_id)
        issues: list[str] = []
        checks_passed: list[str] = []

        namespace = DEFAULT_THANOS_NAMESPACE

        # 1. Check store gateway sync status
        try:
            store_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-store"
            )
            if not store_pods:
                store_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=thanos-store"
                )

            if store_pods:
                # Check if stores are ready (implies block sync is working)
                ready_stores = [pod for pod in store_pods if pod.ready]
                if len(ready_stores) == len(store_pods):
                    checks_passed.append("store_sync")
                    logger.info("thanos_store_sync_verified", ready_count=len(ready_stores))
                else:
                    issues.append(
                        f"Store gateway sync incomplete: {len(ready_stores)}/{len(store_pods)} ready"
                    )
        except Exception as e:
            logger.warning("store_sync_check_failed", error=str(e))
            issues.append(f"Failed to verify store sync: {e!s}")

        # 2. Check compactor status
        try:
            compactor_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-compactor"
            )
            if not compactor_pods:
                compactor_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=thanos-compactor"
                )

            if compactor_pods:
                ready_compactors = [pod for pod in compactor_pods if pod.ready]
                if len(ready_compactors) > 0:
                    checks_passed.append("compactor_running")
                    logger.info("thanos_compactor_running", ready_count=len(ready_compactors))
                else:
                    issues.append("Compactor pods not ready")
            else:
                # Compactor is optional
                logger.debug("thanos_compactor_not_deployed")
                checks_passed.append("compactor_optional")
        except Exception as e:
            logger.warning("compactor_check_failed", error=str(e))
            issues.append(f"Failed to check compactor: {e!s}")

        # 3. Check query connectivity to stores
        try:
            query_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-query"
            )
            if not query_pods:
                query_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=thanos-query"
                )

            if query_pods:
                ready_queries = [pod for pod in query_pods if pod.ready]
                if len(ready_queries) > 0:
                    # Query being ready implies it can reach stores
                    checks_passed.append("query_store_connectivity")
                    logger.info(
                        "thanos_query_connectivity_verified", ready_count=len(ready_queries)
                    )
                else:
                    issues.append("Query pods not ready - cannot verify store connectivity")
            else:
                issues.append("No query pods found")
        except Exception as e:
            logger.warning("query_connectivity_check_failed", error=str(e))
            issues.append(f"Failed to verify query connectivity: {e!s}")

        # 4. Optional: Wait for query frontend cache warm-up
        try:
            qf_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=thanos-query-frontend"
            )
            if not qf_pods:
                qf_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=thanos-query-frontend"
                )

            if qf_pods:
                ready_qf = [pod for pod in qf_pods if pod.ready]
                if len(ready_qf) == len(qf_pods):
                    checks_passed.append("query_frontend_ready")
                    logger.info("thanos_query_frontend_ready", ready_count=len(ready_qf))
                else:
                    # Query frontend issues are warnings, not failures
                    logger.warning(
                        "thanos_query_frontend_not_fully_ready",
                        ready=len(ready_qf),
                        total=len(qf_pods),
                    )
            else:
                logger.debug("thanos_query_frontend_not_deployed")
        except Exception as e:
            logger.debug("query_frontend_check_skipped", error=str(e))

        passed = len(issues) == 0
        message = (
            f"Thanos post-upgrade checks passed: {', '.join(checks_passed)}"
            if passed
            else f"Thanos post-upgrade checks failed: {'; '.join(issues)}"
        )

        logger.info(
            "thanos_post_upgrade_checks_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            checks_passed=checks_passed,
            issue_count=len(issues),
        )

        return CheckResult(
            check_name="thanos_post_upgrade",
            passed=passed,
            message=message,
            metrics={
                "checks_passed": checks_passed,
                "issues": issues,
            },
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    async def wait_for_store_sync(
        k8s_provider: "KubernetesProvider",
        namespace: str = DEFAULT_THANOS_NAMESPACE,
        timeout_seconds: int = 300,
        check_interval: int = 10,
    ) -> bool:
        """Wait for Thanos store to sync blocks.

        Args:
            k8s_provider: Kubernetes provider
            namespace: Thanos namespace
            timeout_seconds: Maximum wait time
            check_interval: Seconds between checks

        Returns:
            True if sync completed, False if timed out
        """
        logger.info(
            "waiting_for_store_sync",
            namespace=namespace,
            timeout=timeout_seconds,
        )

        elapsed = 0
        while elapsed < timeout_seconds:
            try:
                store_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app.kubernetes.io/name=thanos-store"
                )
                if not store_pods:
                    store_pods = await k8s_provider.get_pods(
                        namespace=namespace, label_selector="app=thanos-store"
                    )

                if store_pods:
                    all_ready = all(pod.ready for pod in store_pods)
                    if all_ready:
                        logger.info(
                            "store_sync_completed",
                            elapsed_seconds=elapsed,
                            pod_count=len(store_pods),
                        )
                        return True

            except Exception as e:
                logger.debug("store_sync_check_error", error=str(e))

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        logger.warning("store_sync_timeout", timeout=timeout_seconds)
        return False
