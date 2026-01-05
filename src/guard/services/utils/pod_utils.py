"""Shared utilities for pod retrieval and service health checks.

This module consolidates duplicated pod retrieval logic across services
and adds service-level health check support via HTTP endpoints.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.interfaces.kubernetes_provider import KubernetesProvider, PodInfo

logger = get_logger(__name__)


@dataclass
class PodRetrievalConfig:
    """Configuration for pod retrieval with label selector fallbacks.

    Allows services to define multiple label selectors to try in order,
    supporting different Helm chart conventions.
    """

    component_name: str
    label_selectors: list[str] = field(default_factory=list)
    namespace: str = "monitoring"
    is_required: bool = True

    def __post_init__(self) -> None:
        """Generate default label selectors if none provided."""
        if not self.label_selectors:
            self.label_selectors = [
                f"app.kubernetes.io/name={self.component_name}",
                f"app={self.component_name}",
                f"app.kubernetes.io/component={self.component_name}",
            ]


@dataclass
class ServiceHealthConfig:
    """Configuration for service-level HTTP health checks."""

    service_name: str
    namespace: str
    ready_endpoint: str = "/-/ready"
    health_endpoint: str = "/-/healthy"
    port: int = 9090
    timeout_seconds: int = 10


async def get_pods_with_fallback(
    k8s_provider: "KubernetesProvider",
    config: PodRetrievalConfig,
) -> list["PodInfo"]:
    """Get pods using multiple label selectors with fallback.

    Tries each label selector in order until pods are found.
    This handles variations in Helm chart labeling conventions.

    Args:
        k8s_provider: Kubernetes provider for API access
        config: Pod retrieval configuration with selectors

    Returns:
        List of pods found, empty if none match any selector
    """
    for selector in config.label_selectors:
        try:
            pods = await k8s_provider.get_pods(
                namespace=config.namespace,
                label_selector=selector,
            )
            if pods:
                logger.debug(
                    "pods_found_with_selector",
                    component=config.component_name,
                    selector=selector,
                    pod_count=len(pods),
                )
                return pods
        except Exception as e:
            logger.debug(
                "selector_failed",
                component=config.component_name,
                selector=selector,
                error=str(e),
            )
            continue

    logger.debug(
        "no_pods_found_with_any_selector",
        component=config.component_name,
        selectors_tried=config.label_selectors,
    )
    return []


async def check_pods_ready(
    k8s_provider: "KubernetesProvider",
    config: PodRetrievalConfig,
) -> tuple[bool, list[str], list[str]]:
    """Check if all pods for a component are ready.

    Args:
        k8s_provider: Kubernetes provider for API access
        config: Pod retrieval configuration

    Returns:
        Tuple of (all_ready, ready_pod_names, not_ready_pod_names)
    """
    pods = await get_pods_with_fallback(k8s_provider, config)

    if not pods:
        return False, [], []

    ready_pods = [pod.name for pod in pods if pod.ready]
    not_ready_pods = [pod.name for pod in pods if not pod.ready]

    all_ready = len(not_ready_pods) == 0

    logger.debug(
        "pod_readiness_checked",
        component=config.component_name,
        ready_count=len(ready_pods),
        not_ready_count=len(not_ready_pods),
        all_ready=all_ready,
    )

    return all_ready, ready_pods, not_ready_pods


async def check_service_http_health(
    k8s_provider: "KubernetesProvider",
    config: ServiceHealthConfig,
    check_ready: bool = True,
    check_healthy: bool = False,
) -> tuple[bool, str]:
    """Check service health via HTTP endpoints.

    Executes curl inside a pod to check service readiness/health endpoints.
    This provides deeper validation than pod readiness alone.

    Args:
        k8s_provider: Kubernetes provider for API access
        config: Service health configuration
        check_ready: Whether to check the ready endpoint
        check_healthy: Whether to check the healthy endpoint

    Returns:
        Tuple of (is_healthy, message)
    """
    # Find a running pod for the service
    pod_config = PodRetrievalConfig(
        component_name=config.service_name,
        namespace=config.namespace,
    )
    pods = await get_pods_with_fallback(k8s_provider, pod_config)

    if not pods:
        return False, f"No pods found for service {config.service_name}"

    # Use the first ready pod for health checks
    ready_pods = [p for p in pods if p.ready]
    if not ready_pods:
        return False, f"No ready pods for service {config.service_name}"

    target_pod = ready_pods[0]
    issues: list[str] = []
    checks_passed: list[str] = []

    # Check ready endpoint
    if check_ready:
        try:
            result = await k8s_provider.exec_in_pod(
                namespace=config.namespace,
                pod_name=target_pod.name,
                command=[
                    "wget",
                    "-q",
                    "-O",
                    "-",
                    "--timeout",
                    str(config.timeout_seconds),
                    f"http://localhost:{config.port}{config.ready_endpoint}",
                ],
            )
            # Check if command succeeded (non-empty stdout or no stderr error)
            if result.get("stderr") and "error" in result.get("stderr", "").lower():
                issues.append(f"Ready endpoint failed: {result.get('stderr')}")
            else:
                checks_passed.append("ready_endpoint")
                logger.debug(
                    "ready_endpoint_check_passed",
                    service=config.service_name,
                    pod=target_pod.name,
                )
        except Exception as e:
            # Fallback to curl if wget not available
            try:
                result = await k8s_provider.exec_in_pod(
                    namespace=config.namespace,
                    pod_name=target_pod.name,
                    command=[
                        "curl",
                        "-sf",
                        "--max-time",
                        str(config.timeout_seconds),
                        f"http://localhost:{config.port}{config.ready_endpoint}",
                    ],
                )
                if result.get("stderr") and "error" in result.get("stderr", "").lower():
                    issues.append(f"Ready endpoint failed: {result.get('stderr')}")
                else:
                    checks_passed.append("ready_endpoint")
            except Exception as curl_e:
                logger.warning(
                    "http_health_check_failed",
                    service=config.service_name,
                    endpoint=config.ready_endpoint,
                    wget_error=str(e),
                    curl_error=str(curl_e),
                )
                issues.append(f"Ready endpoint check failed: {curl_e!s}")

    # Check healthy endpoint
    if check_healthy:
        try:
            result = await k8s_provider.exec_in_pod(
                namespace=config.namespace,
                pod_name=target_pod.name,
                command=[
                    "wget",
                    "-q",
                    "-O",
                    "-",
                    "--timeout",
                    str(config.timeout_seconds),
                    f"http://localhost:{config.port}{config.health_endpoint}",
                ],
            )
            if result.get("stderr") and "error" in result.get("stderr", "").lower():
                issues.append(f"Health endpoint failed: {result.get('stderr')}")
            else:
                checks_passed.append("health_endpoint")
        except Exception:
            try:
                result = await k8s_provider.exec_in_pod(
                    namespace=config.namespace,
                    pod_name=target_pod.name,
                    command=[
                        "curl",
                        "-sf",
                        "--max-time",
                        str(config.timeout_seconds),
                        f"http://localhost:{config.port}{config.health_endpoint}",
                    ],
                )
                if result.get("stderr") and "error" in result.get("stderr", "").lower():
                    issues.append(f"Health endpoint failed: {result.get('stderr')}")
                else:
                    checks_passed.append("health_endpoint")
            except Exception as curl_e:
                logger.warning(
                    "http_health_check_failed",
                    service=config.service_name,
                    endpoint=config.health_endpoint,
                    error=str(curl_e),
                )
                issues.append(f"Health endpoint check failed: {curl_e!s}")

    is_healthy = len(issues) == 0
    message = (
        f"Service {config.service_name} healthy: {', '.join(checks_passed)}"
        if is_healthy
        else f"Service {config.service_name} unhealthy: {'; '.join(issues)}"
    )

    return is_healthy, message


async def query_prometheus_targets(
    k8s_provider: "KubernetesProvider",
    namespace: str,
    service_name: str = "prometheus-server",
    port: int = 9090,
) -> tuple[bool, int, int]:
    """Query Prometheus /api/v1/targets to check scrape health.

    Args:
        k8s_provider: Kubernetes provider
        namespace: Prometheus namespace
        service_name: Prometheus service/pod name
        port: Prometheus port

    Returns:
        Tuple of (success, up_targets_count, total_targets_count)
    """
    pod_config = PodRetrievalConfig(
        component_name=service_name,
        namespace=namespace,
    )
    pods = await get_pods_with_fallback(k8s_provider, pod_config)

    if not pods:
        return False, 0, 0

    ready_pods = [p for p in pods if p.ready]
    if not ready_pods:
        return False, 0, 0

    target_pod = ready_pods[0]

    try:
        # Query targets API and count up vs down
        result = await k8s_provider.exec_in_pod(
            namespace=namespace,
            pod_name=target_pod.name,
            command=[
                "wget",
                "-q",
                "-O",
                "-",
                f"http://localhost:{port}/api/v1/targets?state=active",
            ],
        )

        stdout = result.get("stdout", "")
        # Count "health":"up" occurrences
        up_count = stdout.count('"health":"up"')
        # Count total targets (each has "health" field)
        total_count = stdout.count('"health":')

        logger.info(
            "prometheus_targets_queried",
            up_count=up_count,
            total_count=total_count,
            pod=target_pod.name,
        )

        return True, up_count, total_count

    except Exception as e:
        logger.warning("prometheus_targets_query_failed", error=str(e))
        return False, 0, 0


async def query_thanos_stores(
    k8s_provider: "KubernetesProvider",
    namespace: str,
    query_service_name: str = "thanos-query",
    port: int = 10902,
) -> tuple[bool, int, list[str]]:
    """Query Thanos /api/v1/stores to check store connectivity.

    Args:
        k8s_provider: Kubernetes provider
        namespace: Thanos namespace
        query_service_name: Thanos query service/pod name
        port: Thanos query HTTP port

    Returns:
        Tuple of (success, healthy_store_count, unhealthy_stores)
    """
    pod_config = PodRetrievalConfig(
        component_name=query_service_name,
        namespace=namespace,
    )
    pods = await get_pods_with_fallback(k8s_provider, pod_config)

    if not pods:
        return False, 0, []

    ready_pods = [p for p in pods if p.ready]
    if not ready_pods:
        return False, 0, []

    target_pod = ready_pods[0]

    try:
        result = await k8s_provider.exec_in_pod(
            namespace=namespace,
            pod_name=target_pod.name,
            command=[
                "wget",
                "-q",
                "-O",
                "-",
                f"http://localhost:{port}/api/v1/stores",
            ],
        )

        stdout = result.get("stdout", "")
        # Count stores - look for "status" fields
        # "status":"success" in overall response, individual stores have their state
        healthy_count = stdout.count('"lastCheck"')  # Each store has lastCheck

        logger.info(
            "thanos_stores_queried",
            healthy_count=healthy_count,
            pod=target_pod.name,
        )

        return True, healthy_count, []

    except Exception as e:
        logger.warning("thanos_stores_query_failed", error=str(e))
        return False, 0, []
