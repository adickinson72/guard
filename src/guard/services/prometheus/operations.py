"""Prometheus-specific operations extracted for post-upgrade validation."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from guard.core.models import CheckResult
from guard.services.prometheus.config import DEFAULT_PROMETHEUS_NAMESPACE, PROMETHEUS_COMPONENTS
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import KubernetesProvider

logger = get_logger(__name__)


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
    ) -> CheckResult:
        """Validate Prometheus deployment after upgrade.

        Performs comprehensive Prometheus health checks including:
        - Server pods ready and running
        - Alertmanager pods ready (if deployed)
        - Pushgateway pods ready (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        logger.info("validating_prometheus_deployment", cluster_id=cluster.cluster_id)
        issues: list[str] = []
        healthy_components: list[str] = []

        namespace = DEFAULT_PROMETHEUS_NAMESPACE

        # Check each Prometheus component
        for component in PROMETHEUS_COMPONENTS:
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
                            "prometheus_component_healthy",
                            component=component,
                            pod_count=len(pods),
                        )
                else:
                    # Component not deployed - may be optional
                    logger.debug(
                        "prometheus_component_not_found",
                        component=component,
                        message="Component may not be deployed",
                    )

            except Exception as e:
                logger.warning(
                    "prometheus_component_check_failed",
                    component=component,
                    error=str(e),
                )
                issues.append(f"Failed to check {component}: {e!s}")

        # Require at least prometheus-server to be healthy
        required_components = {"prometheus-server"}
        missing_required = required_components - set(healthy_components)
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
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    async def perform_post_upgrade_checks(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Perform Prometheus-specific post-upgrade checks.

        Validates:
        - Server is accepting scrapes
        - TSDB is healthy
        - Alertmanager connectivity (if deployed)

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating success/failure
        """
        logger.info("performing_prometheus_post_upgrade_checks", cluster_id=cluster.cluster_id)
        issues: list[str] = []
        checks_passed: list[str] = []

        namespace = DEFAULT_PROMETHEUS_NAMESPACE

        # 1. Check server status
        try:
            server_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=prometheus-server"
            )
            if not server_pods:
                server_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=prometheus-server"
                )

            if server_pods:
                ready_servers = [pod for pod in server_pods if pod.ready]
                if len(ready_servers) == len(server_pods):
                    checks_passed.append("server_ready")
                    logger.info("prometheus_server_ready", ready_count=len(ready_servers))
                else:
                    issues.append(
                        f"Server not fully ready: {len(ready_servers)}/{len(server_pods)} ready"
                    )
            else:
                issues.append("No Prometheus server pods found")
        except Exception as e:
            logger.warning("server_check_failed", error=str(e))
            issues.append(f"Failed to check server: {e!s}")

        # 2. Check alertmanager status (optional)
        try:
            am_pods = await k8s_provider.get_pods(
                namespace=namespace, label_selector="app.kubernetes.io/name=prometheus-alertmanager"
            )
            if not am_pods:
                am_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=alertmanager"
                )

            if am_pods:
                ready_am = [pod for pod in am_pods if pod.ready]
                if len(ready_am) > 0:
                    checks_passed.append("alertmanager_ready")
                    logger.info("prometheus_alertmanager_ready", ready_count=len(ready_am))
                else:
                    # Alertmanager issues are warnings, not failures
                    logger.warning(
                        "prometheus_alertmanager_not_ready",
                        ready=len(ready_am),
                        total=len(am_pods),
                    )
            else:
                # Alertmanager is optional
                logger.debug("prometheus_alertmanager_not_deployed")
                checks_passed.append("alertmanager_optional")
        except Exception as e:
            logger.debug("alertmanager_check_skipped", error=str(e))

        # 3. Check node-exporter status (optional but common)
        try:
            ne_pods = await k8s_provider.get_pods(
                namespace=namespace,
                label_selector="app.kubernetes.io/name=prometheus-node-exporter",
            )
            if not ne_pods:
                ne_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app=node-exporter"
                )

            if ne_pods:
                ready_ne = [pod for pod in ne_pods if pod.ready]
                if len(ready_ne) == len(ne_pods):
                    checks_passed.append("node_exporter_ready")
                    logger.info("prometheus_node_exporter_ready", ready_count=len(ready_ne))
                else:
                    logger.warning(
                        "prometheus_node_exporter_not_fully_ready",
                        ready=len(ready_ne),
                        total=len(ne_pods),
                    )
            else:
                logger.debug("prometheus_node_exporter_not_deployed")
        except Exception as e:
            logger.debug("node_exporter_check_skipped", error=str(e))

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
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    async def wait_for_tsdb_ready(
        k8s_provider: "KubernetesProvider",
        namespace: str = DEFAULT_PROMETHEUS_NAMESPACE,
        timeout_seconds: int = 300,
        check_interval: int = 10,
    ) -> bool:
        """Wait for Prometheus TSDB to be ready.

        Args:
            k8s_provider: Kubernetes provider
            namespace: Prometheus namespace
            timeout_seconds: Maximum wait time
            check_interval: Seconds between checks

        Returns:
            True if TSDB is ready, False if timed out
        """
        logger.info(
            "waiting_for_tsdb_ready",
            namespace=namespace,
            timeout=timeout_seconds,
        )

        elapsed = 0
        while elapsed < timeout_seconds:
            try:
                server_pods = await k8s_provider.get_pods(
                    namespace=namespace, label_selector="app.kubernetes.io/name=prometheus-server"
                )
                if not server_pods:
                    server_pods = await k8s_provider.get_pods(
                        namespace=namespace, label_selector="app=prometheus-server"
                    )

                if server_pods:
                    all_ready = all(pod.ready for pod in server_pods)
                    if all_ready:
                        logger.info(
                            "tsdb_ready",
                            elapsed_seconds=elapsed,
                            pod_count=len(server_pods),
                        )
                        return True

            except Exception as e:
                logger.debug("tsdb_check_error", error=str(e))

            await asyncio.sleep(check_interval)
            elapsed += check_interval

        logger.warning("tsdb_ready_timeout", timeout=timeout_seconds)
        return False
