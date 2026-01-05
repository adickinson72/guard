"""Thanos-specific operations extracted for post-upgrade validation."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from guard.core.models import CheckResult, ServiceType
from guard.services.thanos.config import (
    DEFAULT_THANOS_CONFIG,
    ThanosServiceConfig,
)
from guard.services.utils.pod_utils import (
    PodRetrievalConfig,
    ServiceHealthConfig,
    check_pods_ready,
    check_service_http_health,
    query_thanos_stores,
)
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


def _get_namespace(cluster: "ClusterConfig", config: ThanosServiceConfig) -> str:
    """Get namespace from cluster config or fall back to default.

    Args:
        cluster: Cluster configuration
        config: Thanos service configuration

    Returns:
        Namespace to use for Thanos operations
    """
    service_version = cluster.get_service_version(ServiceType.THANOS)
    if service_version and service_version.namespace:
        return service_version.namespace
    return config.namespace


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
        config: ThanosServiceConfig | None = None,
    ) -> CheckResult:
        """Validate Thanos deployment after upgrade.

        Performs comprehensive Thanos health checks including:
        - Query pods ready and running with HTTP health check
        - Store pods ready and running
        - Compactor pods ready
        - Query frontend pods ready (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access
            config: Optional service configuration (uses default if not provided)

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        config = config or DEFAULT_THANOS_CONFIG
        namespace = _get_namespace(cluster, config)

        logger.info(
            "validating_thanos_deployment",
            cluster_id=cluster.cluster_id,
            namespace=namespace,
        )
        issues: list[str] = []
        healthy_components: list[str] = []

        # Check each Thanos component using configurable selectors
        for component_name, component_config in config.components.items():
            try:
                pod_config = PodRetrievalConfig(
                    component_name=component_name,
                    label_selectors=component_config.label_selectors,
                    namespace=namespace,
                    is_required=component_config.is_required,
                )

                all_ready, ready_pods, not_ready_pods = await check_pods_ready(
                    k8s_provider, pod_config
                )

                if ready_pods:
                    if not_ready_pods:
                        issues.append(
                            f"{component_name} pods not ready: {', '.join(not_ready_pods)}"
                        )
                    else:
                        healthy_components.append(component_name)
                        logger.info(
                            "thanos_component_healthy",
                            component=component_name,
                            pod_count=len(ready_pods),
                        )

                        # Service-level HTTP health check for query component
                        if component_name == "thanos-query":
                            health_config = ServiceHealthConfig(
                                service_name=component_name,
                                namespace=namespace,
                                port=component_config.http_port,
                                ready_endpoint=component_config.ready_endpoint,
                            )
                            is_healthy, health_msg = await check_service_http_health(
                                k8s_provider, health_config, check_ready=True
                            )
                            if not is_healthy:
                                issues.append(f"Query HTTP health check failed: {health_msg}")
                                logger.warning(
                                    "thanos_query_http_unhealthy",
                                    message=health_msg,
                                )
                            else:
                                logger.info("thanos_query_http_healthy")
                else:
                    if component_config.is_required:
                        issues.append(f"Required component {component_name} not found")
                    else:
                        logger.debug(
                            "thanos_component_not_found",
                            component=component_name,
                            message="Optional component may not be deployed",
                        )

            except Exception as e:
                logger.warning(
                    "thanos_component_check_failed",
                    component=component_name,
                    error=str(e),
                )
                if component_config.is_required:
                    issues.append(f"Failed to check {component_name}: {e!s}")

        # Verify required components are healthy
        required = config.get_required_components()
        missing_required = set(required) - set(healthy_components)
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
            timestamp=datetime.now(UTC),
        )

    @staticmethod
    async def perform_post_upgrade_checks(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
        config: ThanosServiceConfig | None = None,
        wait_for_stabilization: bool = True,
        stabilization_timeout: int = 300,
    ) -> CheckResult:
        """Perform Thanos-specific post-upgrade checks.

        Validates:
        - Store gateway has synced blocks (via /api/v1/stores endpoint)
        - Compactor is running and not stuck
        - Query can reach stores

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access
            config: Optional service configuration
            wait_for_stabilization: Whether to wait for store sync
            stabilization_timeout: Timeout for stabilization wait

        Returns:
            CheckResult indicating success/failure
        """
        config = config or DEFAULT_THANOS_CONFIG
        namespace = _get_namespace(cluster, config)

        logger.info(
            "performing_thanos_post_upgrade_checks",
            cluster_id=cluster.cluster_id,
            namespace=namespace,
        )
        issues: list[str] = []
        checks_passed: list[str] = []

        # 1. Wait for store sync if requested
        if wait_for_stabilization:
            logger.info(
                "waiting_for_thanos_stabilization",
                timeout=stabilization_timeout,
            )
            synced = await ThanosOperations.wait_for_store_sync(
                k8s_provider,
                namespace=namespace,
                timeout_seconds=stabilization_timeout,
                config=config,
            )
            if synced:
                checks_passed.append("store_sync_complete")
            else:
                issues.append("Store sync timed out")

        # 2. Check query HTTP readiness endpoint
        query_config = config.get_component("thanos-query")
        if query_config:
            health_config = ServiceHealthConfig(
                service_name="thanos-query",
                namespace=namespace,
                port=query_config.http_port,
                ready_endpoint=query_config.ready_endpoint,
                health_endpoint=query_config.health_endpoint,
            )
            is_healthy, health_msg = await check_service_http_health(
                k8s_provider, health_config, check_ready=True, check_healthy=True
            )
            if is_healthy:
                checks_passed.append("query_http_ready")
                logger.info("thanos_query_http_ready")
            else:
                issues.append(f"Query HTTP check failed: {health_msg}")

        # 3. Query stores API to verify store connectivity
        try:
            success, store_count, unhealthy_stores = await query_thanos_stores(
                k8s_provider,
                namespace=namespace,
                query_service_name="thanos-query",
                port=query_config.http_port if query_config else 10902,
            )
            if success:
                if store_count > 0:
                    checks_passed.append("stores_connected")
                    logger.info(
                        "thanos_stores_connected",
                        store_count=store_count,
                    )
                else:
                    issues.append("No stores connected to query")
            else:
                issues.append("Failed to query stores API")
        except Exception as e:
            logger.warning("stores_query_failed", error=str(e))
            issues.append(f"Stores API query failed: {e!s}")

        # 4. Check compactor status (optional but important)
        compactor_config = config.get_component("thanos-compactor")
        if compactor_config:
            try:
                pod_config = PodRetrievalConfig(
                    component_name="thanos-compactor",
                    label_selectors=compactor_config.label_selectors,
                    namespace=namespace,
                )
                all_ready, ready_pods, _ = await check_pods_ready(k8s_provider, pod_config)

                if ready_pods:
                    if all_ready:
                        # Check HTTP health
                        health_config = ServiceHealthConfig(
                            service_name="thanos-compactor",
                            namespace=namespace,
                            port=compactor_config.http_port,
                            ready_endpoint=compactor_config.ready_endpoint,
                        )
                        is_healthy, _ = await check_service_http_health(
                            k8s_provider, health_config, check_ready=True
                        )
                        if is_healthy:
                            checks_passed.append("compactor_running")
                            logger.info("thanos_compactor_running")
                    else:
                        issues.append("Compactor pods not ready")
                else:
                    logger.debug("thanos_compactor_not_deployed")
                    checks_passed.append("compactor_optional")
            except Exception as e:
                logger.warning("compactor_check_failed", error=str(e))
                issues.append(f"Failed to check compactor: {e!s}")

        # 5. Check query frontend status (optional)
        qf_config = config.get_component("thanos-query-frontend")
        if qf_config:
            try:
                pod_config = PodRetrievalConfig(
                    component_name="thanos-query-frontend",
                    label_selectors=qf_config.label_selectors,
                    namespace=namespace,
                )
                all_ready, ready_pods, _ = await check_pods_ready(k8s_provider, pod_config)

                if ready_pods:
                    if all_ready:
                        health_config = ServiceHealthConfig(
                            service_name="thanos-query-frontend",
                            namespace=namespace,
                            port=qf_config.http_port,
                            ready_endpoint=qf_config.ready_endpoint,
                        )
                        is_healthy, _ = await check_service_http_health(
                            k8s_provider, health_config, check_ready=True
                        )
                        if is_healthy:
                            checks_passed.append("query_frontend_ready")
                            logger.info("thanos_query_frontend_ready")
                    else:
                        logger.warning("thanos_query_frontend_not_fully_ready")
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
            timestamp=datetime.now(UTC),
        )

    @staticmethod
    async def wait_for_store_sync(
        k8s_provider: "KubernetesProvider",
        namespace: str | None = None,
        timeout_seconds: int = 300,
        check_interval: int = 10,
        config: ThanosServiceConfig | None = None,
    ) -> bool:
        """Wait for Thanos store to sync blocks.

        Checks both pod readiness AND HTTP /-/ready endpoint.

        Args:
            k8s_provider: Kubernetes provider
            namespace: Thanos namespace (uses config default if not provided)
            timeout_seconds: Maximum wait time
            check_interval: Seconds between checks
            config: Optional service configuration

        Returns:
            True if sync completed, False if timed out
        """
        config = config or DEFAULT_THANOS_CONFIG
        namespace = namespace or config.namespace
        store_config = config.get_component("thanos-store")

        logger.info(
            "waiting_for_store_sync",
            namespace=namespace,
            timeout=timeout_seconds,
        )

        elapsed = 0
        while elapsed < timeout_seconds:
            try:
                # Check pod readiness
                pod_config = PodRetrievalConfig(
                    component_name="thanos-store",
                    label_selectors=store_config.label_selectors if store_config else [],
                    namespace=namespace,
                )
                all_ready, ready_pods, _ = await check_pods_ready(k8s_provider, pod_config)

                if ready_pods and all_ready:
                    # Verify with HTTP health check
                    health_config = ServiceHealthConfig(
                        service_name="thanos-store",
                        namespace=namespace,
                        port=store_config.http_port if store_config else 10902,
                    )
                    is_healthy, _ = await check_service_http_health(
                        k8s_provider, health_config, check_ready=True
                    )

                    if is_healthy:
                        logger.info(
                            "store_sync_completed",
                            elapsed_seconds=elapsed,
                            pod_count=len(ready_pods),
                        )
                        return True

            except Exception as e:
                logger.debug("store_sync_check_error", error=str(e))

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        logger.warning("store_sync_timeout", timeout=timeout_seconds)
        return False
