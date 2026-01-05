"""Prometheus-specific operations extracted for post-upgrade validation."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from guard.core.models import CheckResult, ServiceType
from guard.services.prometheus.config import (
    DEFAULT_PROMETHEUS_CONFIG,
    PrometheusServiceConfig,
)
from guard.services.utils.pod_utils import (
    PodRetrievalConfig,
    ServiceHealthConfig,
    check_pods_ready,
    check_service_http_health,
    query_prometheus_targets,
)
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


def _get_namespace(cluster: "ClusterConfig", config: PrometheusServiceConfig) -> str:
    """Get namespace from cluster config or fall back to default.

    Args:
        cluster: Cluster configuration
        config: Prometheus service configuration

    Returns:
        Namespace to use for Prometheus operations
    """
    service_version = cluster.get_service_version(ServiceType.PROMETHEUS)
    if service_version and service_version.namespace:
        return service_version.namespace
    return config.namespace


class PrometheusOperations:
    """Prometheus-specific post-upgrade operations.

    Contains operations for validating Prometheus deployments:
    - validate_deployment: Validates all Prometheus components are healthy
    - perform_post_upgrade_checks: Runs post-upgrade validation checks
    """

    @staticmethod
    async def validate_deployment(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
        config: PrometheusServiceConfig | None = None,
    ) -> CheckResult:
        """Validate Prometheus deployment after upgrade.

        Performs comprehensive Prometheus health checks including:
        - Server pods ready and running
        - HTTP readiness endpoint responding
        - Alertmanager pods ready (if deployed)
        - Pushgateway pods ready (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access
            config: Optional service configuration (uses default if not provided)

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        config = config or DEFAULT_PROMETHEUS_CONFIG
        namespace = _get_namespace(cluster, config)

        logger.info(
            "validating_prometheus_deployment",
            cluster_id=cluster.cluster_id,
            namespace=namespace,
        )
        issues: list[str] = []
        healthy_components: list[str] = []

        # Check each Prometheus component using configurable selectors
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
                            "prometheus_component_healthy",
                            component=component_name,
                            pod_count=len(ready_pods),
                        )

                        # Service-level HTTP health check for server
                        if component_name == "prometheus-server":
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
                                issues.append(f"Server HTTP health check failed: {health_msg}")
                                logger.warning(
                                    "prometheus_server_http_unhealthy",
                                    message=health_msg,
                                )
                            else:
                                logger.info("prometheus_server_http_healthy")
                else:
                    if component_config.is_required:
                        issues.append(f"Required component {component_name} not found")
                    else:
                        logger.debug(
                            "prometheus_component_not_found",
                            component=component_name,
                            message="Optional component may not be deployed",
                        )

            except Exception as e:
                logger.warning(
                    "prometheus_component_check_failed",
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
            f"Prometheus deployment validated: {len(healthy_components)} components healthy"
            if passed
            else f"Prometheus deployment validation failed: {'; '.join(issues)}"
        )

        logger.info(
            "prometheus_deployment_validation_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            healthy_components=healthy_components,
            issue_count=len(issues),
        )

        return CheckResult(
            check_name="prometheus_deployment",
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
        config: PrometheusServiceConfig | None = None,
        wait_for_stabilization: bool = True,
        stabilization_timeout: int = 300,
    ) -> CheckResult:
        """Perform Prometheus-specific post-upgrade checks.

        Validates:
        - Server is accepting scrapes (via /api/v1/targets)
        - TSDB is healthy (via /-/ready endpoint)
        - Alertmanager connectivity (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access
            config: Optional service configuration
            wait_for_stabilization: Whether to wait for TSDB to stabilize
            stabilization_timeout: Timeout for stabilization wait

        Returns:
            CheckResult indicating success/failure
        """
        config = config or DEFAULT_PROMETHEUS_CONFIG
        namespace = _get_namespace(cluster, config)

        logger.info(
            "performing_prometheus_post_upgrade_checks",
            cluster_id=cluster.cluster_id,
            namespace=namespace,
        )
        issues: list[str] = []
        checks_passed: list[str] = []

        # 1. Wait for TSDB stabilization if requested
        if wait_for_stabilization:
            logger.info(
                "waiting_for_prometheus_stabilization",
                timeout=stabilization_timeout,
            )
            stabilized = await PrometheusOperations.wait_for_tsdb_ready(
                k8s_provider,
                namespace=namespace,
                timeout_seconds=stabilization_timeout,
                config=config,
            )
            if stabilized:
                checks_passed.append("tsdb_stabilized")
            else:
                issues.append("TSDB stabilization timed out")

        # 2. Check server HTTP readiness endpoint
        server_config = config.get_component("prometheus-server")
        if server_config:
            health_config = ServiceHealthConfig(
                service_name="prometheus-server",
                namespace=namespace,
                port=server_config.http_port,
                ready_endpoint=server_config.ready_endpoint,
                health_endpoint=server_config.health_endpoint,
            )
            is_healthy, health_msg = await check_service_http_health(
                k8s_provider, health_config, check_ready=True, check_healthy=True
            )
            if is_healthy:
                checks_passed.append("server_http_ready")
                logger.info("prometheus_server_http_ready")
            else:
                issues.append(f"Server HTTP check failed: {health_msg}")

        # 3. Query targets API to verify scraping is working
        try:
            success, up_count, total_count = await query_prometheus_targets(
                k8s_provider,
                namespace=namespace,
                service_name="prometheus-server",
                port=server_config.http_port if server_config else 9090,
            )
            if success:
                if total_count > 0:
                    up_ratio = up_count / total_count if total_count > 0 else 0
                    if up_ratio >= 0.9:  # At least 90% of targets should be up
                        checks_passed.append("scrape_targets_healthy")
                        logger.info(
                            "prometheus_scrape_targets_healthy",
                            up_count=up_count,
                            total_count=total_count,
                            up_ratio=up_ratio,
                        )
                    else:
                        issues.append(
                            f"Too many targets down: {up_count}/{total_count} up ({up_ratio:.1%})"
                        )
                else:
                    logger.warning("prometheus_no_targets_found")
                    checks_passed.append("targets_api_reachable")
            else:
                issues.append("Failed to query targets API")
        except Exception as e:
            logger.warning("targets_query_failed", error=str(e))
            issues.append(f"Targets API query failed: {e!s}")

        # 4. Check alertmanager status (optional)
        am_config = config.get_component("prometheus-alertmanager")
        if am_config:
            try:
                pod_config = PodRetrievalConfig(
                    component_name="prometheus-alertmanager",
                    label_selectors=am_config.label_selectors,
                    namespace=namespace,
                )
                all_ready, ready_pods, _ = await check_pods_ready(k8s_provider, pod_config)

                if ready_pods:
                    if all_ready:
                        # Check HTTP health
                        health_config = ServiceHealthConfig(
                            service_name="prometheus-alertmanager",
                            namespace=namespace,
                            port=am_config.http_port,
                            ready_endpoint=am_config.ready_endpoint,
                        )
                        is_healthy, _ = await check_service_http_health(
                            k8s_provider, health_config, check_ready=True
                        )
                        if is_healthy:
                            checks_passed.append("alertmanager_ready")
                            logger.info("prometheus_alertmanager_ready")
                    else:
                        logger.warning("prometheus_alertmanager_not_fully_ready")
                else:
                    logger.debug("prometheus_alertmanager_not_deployed")
                    checks_passed.append("alertmanager_optional")
            except Exception as e:
                logger.debug("alertmanager_check_skipped", error=str(e))

        passed = len(issues) == 0
        message = (
            f"Prometheus post-upgrade checks passed: {', '.join(checks_passed)}"
            if passed
            else f"Prometheus post-upgrade checks failed: {'; '.join(issues)}"
        )

        logger.info(
            "prometheus_post_upgrade_checks_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            checks_passed=checks_passed,
            issue_count=len(issues),
        )

        return CheckResult(
            check_name="prometheus_post_upgrade",
            passed=passed,
            message=message,
            metrics={
                "checks_passed": checks_passed,
                "issues": issues,
            },
            timestamp=datetime.now(UTC),
        )

    @staticmethod
    async def wait_for_tsdb_ready(
        k8s_provider: "KubernetesProvider",
        namespace: str | None = None,
        timeout_seconds: int = 300,
        check_interval: int = 10,
        config: PrometheusServiceConfig | None = None,
    ) -> bool:
        """Wait for Prometheus TSDB to be ready.

        Checks both pod readiness AND HTTP /-/ready endpoint.

        Args:
            k8s_provider: Kubernetes provider
            namespace: Prometheus namespace (uses config default if not provided)
            timeout_seconds: Maximum wait time
            check_interval: Seconds between checks
            config: Optional service configuration

        Returns:
            True if TSDB is ready, False if timed out
        """
        config = config or DEFAULT_PROMETHEUS_CONFIG
        namespace = namespace or config.namespace
        server_config = config.get_component("prometheus-server")

        logger.info(
            "waiting_for_tsdb_ready",
            namespace=namespace,
            timeout=timeout_seconds,
        )

        elapsed = 0
        while elapsed < timeout_seconds:
            try:
                # Check pod readiness
                pod_config = PodRetrievalConfig(
                    component_name="prometheus-server",
                    label_selectors=server_config.label_selectors if server_config else [],
                    namespace=namespace,
                )
                all_ready, ready_pods, _ = await check_pods_ready(k8s_provider, pod_config)

                if ready_pods and all_ready:
                    # Verify with HTTP health check
                    health_config = ServiceHealthConfig(
                        service_name="prometheus-server",
                        namespace=namespace,
                        port=server_config.http_port if server_config else 9090,
                    )
                    is_healthy, _ = await check_service_http_health(
                        k8s_provider, health_config, check_ready=True
                    )

                    if is_healthy:
                        logger.info(
                            "tsdb_ready",
                            elapsed_seconds=elapsed,
                            pod_count=len(ready_pods),
                        )
                        return True

            except Exception as e:
                logger.debug("tsdb_check_error", error=str(e))

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        logger.warning("tsdb_ready_timeout", timeout=timeout_seconds)
        return False
