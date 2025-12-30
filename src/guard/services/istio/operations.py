"""Istio-specific operations extracted from ValidationEngine."""

import asyncio
import subprocess
import time
from datetime import datetime
from typing import TYPE_CHECKING

from guard.core.models import CheckResult
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.core.models import ClusterConfig
    from guard.interfaces.kubernetes_provider import (
        DaemonSetInfo,
        DeploymentInfo,
        KubernetesProvider,
        StatefulSetInfo,
    )

logger = get_logger(__name__)


class IstioOperations:
    """Istio-specific post-upgrade operations.

    Contains operations that were previously hardcoded in ValidationEngine:
    - validate_deployment: Validates Istio control plane and data plane
    - restart_pods_with_sidecars: Restarts workloads with Istio sidecars
    - has_istio_sidecar: Detects Istio sidecar presence in workloads
    """

    @staticmethod
    def has_istio_sidecar(
        workload: "DeploymentInfo | StatefulSetInfo | DaemonSetInfo",
    ) -> bool:
        """Check if a workload has an Istio sidecar.

        Works with normalized workload info dataclasses that have
        containers list and annotations dict.

        Args:
            workload: Normalized workload info (DeploymentInfo, StatefulSetInfo, DaemonSetInfo)

        Returns:
            True if workload has istio-proxy sidecar
        """
        try:
            # Check for istio-proxy container
            if workload.containers and "istio-proxy" in workload.containers:
                return True

            # Check for Istio injection annotations
            if workload.annotations:
                if "sidecar.istio.io/status" in workload.annotations:
                    return True
                if workload.annotations.get("sidecar.istio.io/inject") == "true":
                    return True

            return False
        except Exception as e:
            logger.warning("sidecar_detection_failed", error=str(e))
            return False

    @staticmethod
    async def validate_deployment(
        cluster: "ClusterConfig",
        k8s_provider: "KubernetesProvider",
    ) -> CheckResult:
        """Validate Istio deployment after upgrade.

        Performs comprehensive Istio health checks including:
        - istiod pods ready and running
        - Gateway pods ready and running
        - istioctl analyze for configuration errors
        - istioctl proxy-status for data plane connectivity

        Args:
            cluster: Cluster configuration
            k8s_provider: Kubernetes provider for API access

        Returns:
            CheckResult indicating pass/fail with detailed messages
        """
        logger.info("validating_istio_deployment", cluster_id=cluster.cluster_id)
        issues: list[str] = []

        try:
            # 1. Check istiod pods (control plane)
            try:
                istiod_pods = await k8s_provider.get_pods(
                    namespace="istio-system", label_selector="app=istiod"
                )
                if not istiod_pods:
                    issues.append("No istiod pods found in istio-system namespace")
                else:
                    not_ready = []
                    for pod in istiod_pods:
                        # Use normalized PodInfo - ready is a direct attribute
                        if not pod.ready:
                            not_ready.append(pod.name)

                    if not_ready:
                        issues.append(f"istiod pods not ready: {', '.join(not_ready)}")
                    else:
                        logger.info("istiod_pods_ready", count=len(istiod_pods))
            except Exception as e:
                issues.append(f"Failed to check istiod pods: {e!s}")

            # 2. Check gateway pods
            try:
                gateway_pods = await k8s_provider.get_pods(
                    namespace="istio-system", label_selector="istio=ingressgateway"
                )
                # Also check for alternative gateway labels
                if not gateway_pods:
                    gateway_pods = await k8s_provider.get_pods(
                        namespace="istio-system", label_selector="app=istio-ingressgateway"
                    )

                if gateway_pods:
                    not_ready = []
                    for pod in gateway_pods:
                        # Use normalized PodInfo - ready is a direct attribute
                        if not pod.ready:
                            not_ready.append(pod.name)

                    if not_ready:
                        issues.append(f"Gateway pods not ready: {', '.join(not_ready)}")
                    else:
                        logger.info("gateway_pods_ready", count=len(gateway_pods))
            except Exception as e:
                logger.warning("gateway_check_failed", error=str(e))
                # Gateways are optional, don't fail validation

            # 3. Run istioctl analyze for configuration issues
            try:
                analyze_result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["istioctl", "analyze", "--namespace", "istio-system"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    ),
                )

                if analyze_result.returncode != 0 and analyze_result.stdout:
                    # Parse output for errors (not warnings)
                    output_lines = analyze_result.stdout.strip().split("\n")
                    errors = [line for line in output_lines if "[Error]" in line or "Error" in line]
                    if errors:
                        issues.append(f"istioctl analyze found errors: {'; '.join(errors[:3])}")
                    else:
                        logger.info("istioctl_analyze_warnings_only")
                elif analyze_result.returncode == 0:
                    logger.info("istioctl_analyze_passed")
            except subprocess.TimeoutExpired:
                issues.append("istioctl analyze timed out after 60s")
            except FileNotFoundError:
                logger.warning(
                    "istioctl_not_found", message="istioctl not in PATH, skipping analyze"
                )
            except Exception as e:
                logger.warning("istioctl_analyze_failed", error=str(e))

            # 4. Check proxy status (data plane connectivity)
            try:
                proxy_status_result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["istioctl", "proxy-status"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    ),
                )

                if proxy_status_result.returncode == 0 and proxy_status_result.stdout:
                    # Parse output to check for NOT SYNCED proxies
                    output_lines = proxy_status_result.stdout.strip().split("\n")
                    if len(output_lines) > 1:  # Has header + data
                        not_synced = []
                        for line in output_lines[1:]:  # Skip header
                            if line and "SYNCED" not in line and line.strip():
                                parts = line.split()
                                if parts:
                                    not_synced.append(parts[0])

                        if not_synced:
                            issues.append(
                                f"Proxies not synced: {len(not_synced)} proxies "
                                f"(examples: {', '.join(not_synced[:3])})"
                            )
                        else:
                            logger.info("all_proxies_synced")
            except subprocess.TimeoutExpired:
                issues.append("istioctl proxy-status timed out after 60s")
            except FileNotFoundError:
                logger.warning("istioctl_not_found_proxy_status")
            except Exception as e:
                logger.warning("istioctl_proxy_status_failed", error=str(e))

        except Exception as e:
            issues.append(f"Istio validation failed: {e!s}")
            logger.error("istio_validation_exception", error=str(e))

        passed = len(issues) == 0
        message = (
            "Istio deployment validated successfully"
            if passed
            else f"Istio deployment validation failed: {'; '.join(issues)}"
        )

        logger.info(
            "istio_deployment_validation_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            issue_count=len(issues),
        )

        return CheckResult(
            check_name="istio_deployment",
            passed=passed,
            message=message,
            metrics={"issues": issues},
            timestamp=datetime.utcnow(),
        )

    @staticmethod
    async def restart_pods_with_sidecars(
        k8s_provider: "KubernetesProvider",
        namespace: str | None = None,
        wave_size: int = 5,
        wait_for_ready: bool = True,
        readiness_timeout: int = 300,
    ) -> CheckResult:
        """Restart all pods with Istio sidecars after upgrade.

        This ensures sidecar proxy versions match the new control plane version.
        Uses progressive wave-based rolling restart strategy to minimize disruption.

        Only restarts workloads that actually have Istio sidecars (istio-proxy container).
        Supports both istio-injection=enabled and istio.io/rev labels.

        Args:
            k8s_provider: Kubernetes provider instance
            namespace: Specific namespace (None = all namespaces with istio labels)
            wave_size: Number of workloads to restart per wave (default: 5)
            wait_for_ready: Wait for workloads to be ready between waves (default: True)
            readiness_timeout: Timeout in seconds to wait for readiness (default: 300)

        Returns:
            CheckResult indicating success/failure
        """
        logger.info(
            "restarting_pods_with_sidecars",
            namespace=namespace,
            wave_size=wave_size,
            wait_for_ready=wait_for_ready,
        )

        try:
            restarted_resources: list[str] = []
            failed_resources: list[str] = []

            # Get namespaces with Istio labels (injection or revision-based)
            if namespace:
                namespaces_to_process = [namespace]
                logger.info("processing_single_namespace", namespace=namespace)
            else:
                # Query for both istio-injection=enabled and istio.io/rev labels
                # get_namespaces returns list[str] directly
                injection_ns = await k8s_provider.get_namespaces(
                    label_selector="istio-injection=enabled"
                )
                revision_ns = await k8s_provider.get_namespaces(label_selector="istio.io/rev")

                # Combine and deduplicate - both are list[str]
                ns_names = set(injection_ns + revision_ns)
                namespaces_to_process = sorted(ns_names)
                logger.info(
                    "found_istio_namespaces",
                    count=len(namespaces_to_process),
                    namespaces=list(namespaces_to_process),
                )

            # Collect all workloads with sidecars across namespaces
            # Store (kind, namespace, name) tuples
            workloads_to_restart: list[tuple[str, str, str]] = []

            for ns in namespaces_to_process:
                logger.info("scanning_namespace_for_sidecars", namespace=ns)

                # Check Deployments
                try:
                    deployments = await k8s_provider.get_deployments(namespace=ns)
                    for deployment in deployments:
                        if IstioOperations.has_istio_sidecar(deployment):
                            workloads_to_restart.append(("Deployment", ns, deployment.name))
                except Exception as e:
                    logger.error("failed_to_scan_deployments", namespace=ns, error=str(e))

                # Check StatefulSets
                try:
                    statefulsets = await k8s_provider.get_statefulsets(namespace=ns)
                    for sts in statefulsets:
                        if IstioOperations.has_istio_sidecar(sts):
                            workloads_to_restart.append(("StatefulSet", ns, sts.name))
                except Exception as e:
                    logger.error("failed_to_scan_statefulsets", namespace=ns, error=str(e))

                # Check DaemonSets
                try:
                    daemonsets = await k8s_provider.get_daemonsets(namespace=ns)
                    for ds in daemonsets:
                        if IstioOperations.has_istio_sidecar(ds):
                            workloads_to_restart.append(("DaemonSet", ns, ds.name))
                except Exception as e:
                    logger.error("failed_to_scan_daemonsets", namespace=ns, error=str(e))

            total_workloads = len(workloads_to_restart)
            logger.info(
                "workloads_with_sidecars_identified",
                total=total_workloads,
                wave_size=wave_size,
                estimated_waves=(total_workloads + wave_size - 1) // wave_size
                if total_workloads
                else 0,
            )

            # Restart workloads in waves
            for wave_start in range(0, total_workloads, wave_size):
                wave_end = min(wave_start + wave_size, total_workloads)
                wave_number = (wave_start // wave_size) + 1
                total_waves = (total_workloads + wave_size - 1) // wave_size

                logger.info(
                    "starting_restart_wave",
                    wave=wave_number,
                    total_waves=total_waves,
                    workloads_in_wave=wave_end - wave_start,
                )

                wave_workloads = workloads_to_restart[wave_start:wave_end]
                wave_restarted: list[tuple[str, str, str]] = []

                # Restart all workloads in this wave
                for kind, ns, name in wave_workloads:
                    try:
                        if kind == "Deployment":
                            await k8s_provider.restart_deployment(name=name, namespace=ns)
                        elif kind == "StatefulSet":
                            await k8s_provider.restart_statefulset(name=name, namespace=ns)
                        elif kind == "DaemonSet":
                            await k8s_provider.restart_daemonset(name=name, namespace=ns)

                        resource_id = f"{kind}/{ns}/{name}"
                        restarted_resources.append(resource_id)
                        wave_restarted.append((kind, ns, name))
                        logger.info(
                            "workload_restarted",
                            kind=kind,
                            namespace=ns,
                            name=name,
                            wave=wave_number,
                        )
                    except Exception as e:
                        resource_id = f"{kind}/{ns}/{name}"
                        failed_resources.append(resource_id)
                        logger.error(
                            "workload_restart_failed",
                            kind=kind,
                            namespace=ns,
                            name=name,
                            wave=wave_number,
                            error=str(e),
                        )

                # Wait for workloads in this wave to be ready
                if wait_for_ready and wave_restarted:
                    logger.info(
                        "waiting_for_wave_readiness",
                        wave=wave_number,
                        workload_count=len(wave_restarted),
                    )

                    start_time = time.time()
                    all_ready = False

                    while (time.time() - start_time) < readiness_timeout:
                        ready_count = 0

                        for kind, ns, name in wave_restarted:
                            try:
                                if kind == "Deployment":
                                    if await k8s_provider.check_deployment_ready(
                                        name=name, namespace=ns
                                    ):
                                        ready_count += 1
                                elif kind == "StatefulSet":
                                    if await k8s_provider.check_statefulset_ready(
                                        name=name, namespace=ns
                                    ):
                                        ready_count += 1
                                elif kind == "DaemonSet":
                                    if await k8s_provider.check_daemonset_ready(
                                        name=name, namespace=ns
                                    ):
                                        ready_count += 1
                                else:
                                    # Unknown workload type, assume ready
                                    ready_count += 1
                            except Exception as e:
                                logger.debug(
                                    "readiness_check_failed",
                                    kind=kind,
                                    namespace=ns,
                                    name=name,
                                    error=str(e),
                                )

                        if ready_count == len(wave_restarted):
                            all_ready = True
                            logger.info(
                                "wave_ready",
                                wave=wave_number,
                                duration=int(time.time() - start_time),
                            )
                            break

                        await asyncio.sleep(10)

                    if not all_ready:
                        logger.warning(
                            "wave_readiness_timeout",
                            wave=wave_number,
                            ready=ready_count,
                            total=len(wave_restarted),
                        )

            # Build result message
            message_parts = [f"Restarted {len(restarted_resources)} resources with Istio sidecars"]
            if failed_resources:
                message_parts.append(f"Failed to restart {len(failed_resources)} resources")

            passed = len(failed_resources) == 0

            logger.info(
                "pod_restart_completed",
                restarted_count=len(restarted_resources),
                failed_count=len(failed_resources),
                passed=passed,
            )

            return CheckResult(
                check_name="restart_pods_with_sidecars",
                passed=passed,
                message=". ".join(message_parts),
                metrics={
                    "restarted_resources": restarted_resources,
                    "failed_resources": failed_resources,
                },
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            logger.error("pod_restart_failed", error=str(e))
            return CheckResult(
                check_name="restart_pods_with_sidecars",
                passed=False,
                message=f"Failed to restart pods with sidecars: {e!s}",
                timestamp=datetime.utcnow(),
            )
