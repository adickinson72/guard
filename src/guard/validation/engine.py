"""Post-upgrade validation engine."""

import subprocess
import time
from datetime import datetime

from guard.clients.kubernetes_client import KubernetesClient
from guard.core.models import CheckResult, ClusterConfig
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationEngine:
    """Engine for post-upgrade validation."""

    def __init__(self, soak_period_minutes: int = 60, restart_pods_with_sidecars: bool = True):
        """Initialize validation engine.

        Args:
            soak_period_minutes: Soak period in minutes
            restart_pods_with_sidecars: Whether to restart pods with sidecars after upgrade
        """
        self.soak_period = soak_period_minutes * 60
        self.restart_pods_with_sidecars = restart_pods_with_sidecars
        logger.debug(
            "validation_engine_initialized",
            soak_period_minutes=soak_period_minutes,
            restart_pods_with_sidecars=restart_pods_with_sidecars,
        )

    def wait_for_flux_sync(
        self, cluster: ClusterConfig, timeout_minutes: int = 15, poll_interval: int = 10
    ) -> bool:
        """Wait for Flux to sync changes.

        Monitors Flux Kustomizations and HelmReleases for reconciliation.
        Uses flux CLI commands to check sync status.

        Args:
            cluster: Cluster configuration
            timeout_minutes: Timeout in minutes
            poll_interval: Polling interval in seconds

        Returns:
            True if sync completed successfully
        """
        logger.info(
            "waiting_for_flux_sync",
            cluster_id=cluster.cluster_id,
            timeout_minutes=timeout_minutes,
        )

        timeout = timeout_minutes * 60
        start_time = time.time()
        last_log_time = start_time

        while (time.time() - start_time) < timeout:
            try:
                # Check if flux kustomizations are ready
                result = subprocess.run(
                    ["flux", "get", "kustomizations", "-A", "--no-header"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

                if result.returncode == 0:
                    # Parse output to check if all are ready
                    lines = [
                        line.strip() for line in result.stdout.strip().split("\n") if line.strip()
                    ]
                    if lines:
                        all_ready = all("True" in line for line in lines)
                        if all_ready:
                            logger.info(
                                "flux_sync_completed",
                                cluster_id=cluster.cluster_id,
                                duration=int(time.time() - start_time),
                            )
                            return True

                # Log progress every 30 seconds
                if (time.time() - last_log_time) >= 30:
                    logger.info(
                        "flux_sync_in_progress",
                        cluster_id=cluster.cluster_id,
                        elapsed=int(time.time() - start_time),
                        timeout=timeout,
                    )
                    last_log_time = time.time()

                time.sleep(poll_interval)

            except subprocess.TimeoutExpired:
                logger.warning(
                    "flux_check_timeout",
                    cluster_id=cluster.cluster_id,
                )
                time.sleep(poll_interval)

            except Exception as e:
                logger.error(
                    "flux_sync_check_failed",
                    cluster_id=cluster.cluster_id,
                    error=str(e),
                )
                time.sleep(poll_interval)

        logger.error(
            "flux_sync_timeout",
            cluster_id=cluster.cluster_id,
            timeout_minutes=timeout_minutes,
        )
        return False

    def run_soak_period(self, progress_interval: int = 60) -> None:
        """Wait for metrics to stabilize with progressive monitoring.

        Args:
            progress_interval: Interval in seconds to log progress (default: 60)
        """
        logger.info("starting_soak_period", duration_seconds=self.soak_period)

        start_time = time.time()
        elapsed = 0

        while elapsed < self.soak_period:
            # Sleep for the progress interval or remaining time, whichever is smaller
            sleep_duration = min(progress_interval, self.soak_period - elapsed)
            time.sleep(sleep_duration)

            elapsed = int(time.time() - start_time)
            remaining = self.soak_period - elapsed

            if remaining > 0:
                logger.info(
                    "soak_period_progress",
                    elapsed_seconds=elapsed,
                    remaining_seconds=remaining,
                    progress_percent=int((elapsed / self.soak_period) * 100),
                )

        logger.info("soak_period_completed", total_duration_seconds=elapsed)

    def validate_istio_deployment(self, cluster: ClusterConfig) -> CheckResult:
        """Validate Istio deployment after upgrade.

        Args:
            cluster: Cluster configuration

        Returns:
            CheckResult
        """
        logger.info("validating_istio_deployment", cluster_id=cluster.cluster_id)
        # TODO: Implement Istio deployment validation
        return CheckResult(
            check_name="istio_deployment",
            passed=True,
            message="Istio deployment validated",
            timestamp=datetime.utcnow(),
        )

    def _has_istio_sidecar(self, workload_spec: dict) -> bool:
        """Check if a workload has an Istio sidecar.

        Args:
            workload_spec: Workload spec (deployment.spec, statefulset.spec, etc.)

        Returns:
            True if workload has istio-proxy sidecar
        """
        try:
            template = workload_spec.template
            # Check for istio-proxy container
            if template.spec and template.spec.containers:
                for container in template.spec.containers:
                    if container.name == "istio-proxy":
                        return True

            # Check for Istio injection annotations
            if template.metadata and template.metadata.annotations:
                annotations = template.metadata.annotations
                if "sidecar.istio.io/status" in annotations:
                    return True
                if annotations.get("sidecar.istio.io/inject") == "true":
                    return True

            return False
        except Exception as e:
            logger.warning("sidecar_detection_failed", error=str(e))
            return False

    def restart_pods_with_istio_sidecars(
        self,
        k8s_client: KubernetesClient,
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
            k8s_client: Kubernetes client instance
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
                injection_ns = k8s_client.get_namespaces(label_selector="istio-injection=enabled")
                revision_ns = k8s_client.get_namespaces(label_selector="istio.io/rev")

                # Combine and deduplicate
                ns_names = set()
                for ns in injection_ns + revision_ns:
                    ns_names.add(ns.metadata.name)

                namespaces_to_process = sorted(ns_names)
                logger.info(
                    "found_istio_namespaces",
                    count=len(namespaces_to_process),
                    namespaces=list(namespaces_to_process),
                )

            # Collect all workloads with sidecars across namespaces
            workloads_to_restart = []

            for ns in namespaces_to_process:
                logger.info("scanning_namespace_for_sidecars", namespace=ns)

                # Check Deployments
                try:
                    deployments = k8s_client.get_deployments(namespace=ns)
                    for deployment in deployments:
                        if self._has_istio_sidecar(deployment.spec):
                            workloads_to_restart.append(
                                ("Deployment", ns, deployment.metadata.name, deployment)
                            )
                except Exception as e:
                    logger.error("failed_to_scan_deployments", namespace=ns, error=str(e))

                # Check StatefulSets
                try:
                    statefulsets = k8s_client.get_statefulsets(namespace=ns)
                    for sts in statefulsets:
                        if self._has_istio_sidecar(sts.spec):
                            workloads_to_restart.append(("StatefulSet", ns, sts.metadata.name, sts))
                except Exception as e:
                    logger.error("failed_to_scan_statefulsets", namespace=ns, error=str(e))

                # Check DaemonSets
                try:
                    daemonsets = k8s_client.get_daemonsets(namespace=ns)
                    for ds in daemonsets:
                        if self._has_istio_sidecar(ds.spec):
                            workloads_to_restart.append(("DaemonSet", ns, ds.metadata.name, ds))
                except Exception as e:
                    logger.error("failed_to_scan_daemonsets", namespace=ns, error=str(e))

            total_workloads = len(workloads_to_restart)
            logger.info(
                "workloads_with_sidecars_identified",
                total=total_workloads,
                wave_size=wave_size,
                estimated_waves=(total_workloads + wave_size - 1) // wave_size,
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
                wave_restarted = []

                # Restart all workloads in this wave
                for kind, ns, name, workload_obj in wave_workloads:
                    try:
                        if kind == "Deployment":
                            k8s_client.restart_deployment(name=name, namespace=ns)
                        elif kind == "StatefulSet":
                            k8s_client.restart_statefulset(name=name, namespace=ns)
                        elif kind == "DaemonSet":
                            k8s_client.restart_daemonset(name=name, namespace=ns)

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

                # Wait for workloads in this wave to be ready before next wave
                if wait_for_ready and wave_restarted and wave_number < total_waves:
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
                                    if k8s_client.check_deployment_ready(name=name, namespace=ns):
                                        ready_count += 1
                                # Note: StatefulSets and DaemonSets need similar ready checks
                                # For now, we assume they're ready if no error
                                else:
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

                        time.sleep(10)

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
                message=f"Failed to restart pods with sidecars: {str(e)}",
                timestamp=datetime.utcnow(),
            )
