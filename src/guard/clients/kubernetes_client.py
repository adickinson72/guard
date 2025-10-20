"""Kubernetes client for cluster operations."""

from datetime import datetime

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream
from kubernetes.client.models import (
    V1DaemonSet,
    V1Deployment,
    V1MutatingWebhookConfiguration,
    V1Namespace,
    V1Node,
    V1Pod,
    V1StatefulSet,
    V1ValidatingWebhookConfiguration,
)

from guard.core.exceptions import KubernetesError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class KubernetesClient:
    """Kubernetes client wrapper."""

    def __init__(self, kubeconfig_path: str | None = None, context: str | None = None):
        """Initialize Kubernetes client.

        Args:
            kubeconfig_path: Path to kubeconfig file (optional)
            context: Kubernetes context to use (optional)
        """
        try:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path, context=context)
            else:
                # Try to load from default location or in-cluster config
                try:
                    config.load_kube_config(context=context)
                except config.ConfigException:
                    config.load_incluster_config()

            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.admissionregistration_v1 = client.AdmissionregistrationV1Api()

            logger.debug("k8s_client_initialized", context=context)

        except Exception as e:
            logger.error("k8s_client_initialization_failed", error=str(e))
            raise KubernetesError("Failed to initialize Kubernetes client") from e

    def get_nodes(self) -> list[V1Node]:
        """Get all nodes in the cluster.

        Returns:
            List of V1Node objects

        Raises:
            KubernetesError: If nodes cannot be retrieved
        """
        try:
            logger.debug("getting_nodes")
            response = self.core_v1.list_node()
            nodes = response.items

            logger.info("nodes_retrieved", count=len(nodes))
            return nodes

        except ApiException as e:
            logger.error("get_nodes_failed", status=e.status, reason=e.reason)
            raise KubernetesError(f"Failed to get nodes: {e.reason}") from e

    def check_nodes_ready(self) -> tuple[bool, list[str]]:
        """Check if all nodes are in Ready state.

        Returns:
            Tuple of (all_ready: bool, unready_nodes: list)
        """
        try:
            nodes = self.get_nodes()
            unready_nodes = []

            for node in nodes:
                ready = False
                for condition in node.status.conditions:
                    if condition.type == "Ready":
                        ready = condition.status == "True"
                        break

                if not ready:
                    unready_nodes.append(node.metadata.name)

            all_ready = len(unready_nodes) == 0
            logger.info(
                "nodes_ready_check",
                all_ready=all_ready,
                unready_count=len(unready_nodes),
            )

            return all_ready, unready_nodes

        except Exception as e:
            logger.error("nodes_ready_check_failed", error=str(e))
            raise KubernetesError("Failed to check node readiness") from e

    def get_pods(
        self, namespace: str = "default", label_selector: str | None = None
    ) -> list[V1Pod]:
        """Get pods in a namespace.

        Args:
            namespace: Namespace to query
            label_selector: Label selector (e.g., "app=istiod")

        Returns:
            List of V1Pod objects

        Raises:
            KubernetesError: If pods cannot be retrieved
        """
        try:
            logger.debug("getting_pods", namespace=namespace, selector=label_selector)

            response = self.core_v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector
            )
            pods = response.items

            logger.info("pods_retrieved", namespace=namespace, count=len(pods))
            return pods

        except ApiException as e:
            logger.error(
                "get_pods_failed",
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to get pods in {namespace}: {e.reason}") from e

    def check_pods_ready(
        self, namespace: str = "default", label_selector: str | None = None
    ) -> tuple[bool, list[str]]:
        """Check if all pods are ready.

        Uses pod.status.conditions to determine readiness (type=="Ready")
        and validates both init containers and regular containers.

        Args:
            namespace: Namespace to check
            label_selector: Label selector

        Returns:
            Tuple of (all_ready: bool, unready_pods: list)
        """
        try:
            pods = self.get_pods(namespace=namespace, label_selector=label_selector)
            unready_pods = []

            for pod in pods:
                # Check if pod is ready using conditions (recommended approach)
                is_ready = False
                if pod.status.conditions:
                    for condition in pod.status.conditions:
                        if condition.type == "Ready":
                            is_ready = condition.status == "True"
                            break

                if not is_ready:
                    unready_pods.append(pod.metadata.name)
                    continue

                # Additional check for init containers if present
                if pod.status.init_container_statuses:
                    all_init_completed = all(
                        container.ready or container.state.terminated is not None
                        for container in pod.status.init_container_statuses
                    )
                    if not all_init_completed:
                        # If init containers aren't ready, pod might not be truly ready
                        logger.debug(
                            "pod_init_containers_pending",
                            namespace=namespace,
                            pod=pod.metadata.name,
                        )

            all_ready = len(unready_pods) == 0
            logger.info(
                "pods_ready_check",
                namespace=namespace,
                all_ready=all_ready,
                unready_count=len(unready_pods),
            )

            return all_ready, unready_pods

        except Exception as e:
            logger.error("pods_ready_check_failed", namespace=namespace, error=str(e))
            raise KubernetesError("Failed to check pod readiness") from e

    def get_deployment(self, name: str, namespace: str = "default") -> V1Deployment:
        """Get a deployment.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            V1Deployment object

        Raises:
            KubernetesError: If deployment cannot be retrieved
        """
        try:
            logger.debug("getting_deployment", name=name, namespace=namespace)

            deployment = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            logger.info("deployment_retrieved", name=name, namespace=namespace)
            return deployment

        except ApiException as e:
            if e.status == 404:
                logger.warning("deployment_not_found", name=name, namespace=namespace)
                raise KubernetesError(f"Deployment {name} not found in {namespace}") from e

            logger.error(
                "get_deployment_failed",
                name=name,
                namespace=namespace,
                status=e.status,
            )
            raise KubernetesError(f"Failed to get deployment {name}: {e.reason}") from e

    def check_deployment_ready(self, name: str, namespace: str = "default") -> bool:
        """Check if deployment is ready.

        Uses deployment.status.conditions (Available=True), observedGeneration,
        and updated_replicas to accurately determine deployment readiness.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            True if deployment is ready
        """
        try:
            deployment = self.get_deployment(name=name, namespace=namespace)

            # Check if the deployment has been observed at the current generation
            spec_generation = deployment.metadata.generation or 0
            observed_generation = deployment.status.observed_generation or 0

            if observed_generation < spec_generation:
                logger.debug(
                    "deployment_generation_mismatch",
                    name=name,
                    namespace=namespace,
                    spec=spec_generation,
                    observed=observed_generation,
                )
                return False

            # Check deployment conditions for Available status
            is_available = False
            if deployment.status.conditions:
                for condition in deployment.status.conditions:
                    if condition.type == "Available":
                        is_available = condition.status == "True"
                        break

            # Check replica counts
            desired = deployment.spec.replicas or 0
            ready = deployment.status.ready_replicas or 0
            updated = deployment.status.updated_replicas or 0
            available = deployment.status.available_replicas or 0

            # Deployment is ready if:
            # 1. Available condition is True
            # 2. All replicas are updated
            # 3. All replicas are ready
            # 4. All replicas are available
            is_ready = (
                is_available
                and updated == desired
                and ready == desired
                and available == desired
                and desired > 0
            )

            logger.info(
                "deployment_ready_check",
                name=name,
                namespace=namespace,
                is_ready=is_ready,
                is_available=is_available,
                ready=ready,
                updated=updated,
                available=available,
                desired=desired,
            )

            return is_ready

        except Exception as e:
            logger.error(
                "deployment_ready_check_failed",
                name=name,
                namespace=namespace,
                error=str(e),
            )
            raise KubernetesError("Failed to check deployment readiness") from e

    def get_validating_webhook_configurations(
        self,
    ) -> list[V1ValidatingWebhookConfiguration]:
        """Get all validating webhook configurations.

        Returns:
            List of V1ValidatingWebhookConfiguration objects

        Raises:
            KubernetesError: If webhooks cannot be retrieved
        """
        try:
            logger.debug("getting_validating_webhooks")

            response = self.admissionregistration_v1.list_validating_webhook_configuration()
            webhooks = response.items

            logger.info("validating_webhooks_retrieved", count=len(webhooks))
            return webhooks

        except ApiException as e:
            logger.error("get_validating_webhooks_failed", status=e.status)
            raise KubernetesError(f"Failed to get validating webhooks: {e.reason}") from e

    def get_mutating_webhook_configurations(
        self,
    ) -> list[V1MutatingWebhookConfiguration]:
        """Get all mutating webhook configurations.

        Returns:
            List of V1MutatingWebhookConfiguration objects

        Raises:
            KubernetesError: If webhooks cannot be retrieved
        """
        try:
            logger.debug("getting_mutating_webhooks")

            response = self.admissionregistration_v1.list_mutating_webhook_configuration()
            webhooks = response.items

            logger.info("mutating_webhooks_retrieved", count=len(webhooks))
            return webhooks

        except ApiException as e:
            logger.error("get_mutating_webhooks_failed", status=e.status)
            raise KubernetesError(f"Failed to get mutating webhooks: {e.reason}") from e

    def get_namespaces(self, label_selector: str | None = None) -> list[V1Namespace]:
        """Get all namespaces in the cluster.

        Args:
            label_selector: Label selector (e.g., "istio-injection=enabled")

        Returns:
            List of V1Namespace objects

        Raises:
            KubernetesError: If namespaces cannot be retrieved
        """
        try:
            logger.debug("getting_namespaces", selector=label_selector)
            response = self.core_v1.list_namespace(label_selector=label_selector)
            namespaces = response.items

            logger.info("namespaces_retrieved", count=len(namespaces))
            return namespaces

        except ApiException as e:
            logger.error("get_namespaces_failed", status=e.status, reason=e.reason)
            raise KubernetesError(f"Failed to get namespaces: {e.reason}") from e

    def restart_deployment(self, name: str, namespace: str) -> bool:
        """Restart a deployment using rollout restart strategy.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesError: If restart fails
        """
        try:
            logger.info("restarting_deployment", name=name, namespace=namespace)

            # Patch deployment with restart annotation
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
                    }
                }
            }

            self.apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)

            logger.info("deployment_restart_initiated", name=name, namespace=namespace)
            return True

        except ApiException as e:
            logger.error(
                "deployment_restart_failed",
                name=name,
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to restart deployment {name}: {e.reason}") from e

    def restart_statefulset(self, name: str, namespace: str) -> bool:
        """Restart a statefulset using rollout restart strategy.

        Args:
            name: StatefulSet name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesError: If restart fails
        """
        try:
            logger.info("restarting_statefulset", name=name, namespace=namespace)

            # Patch statefulset with restart annotation
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
                    }
                }
            }

            self.apps_v1.patch_namespaced_stateful_set(name=name, namespace=namespace, body=body)

            logger.info("statefulset_restart_initiated", name=name, namespace=namespace)
            return True

        except ApiException as e:
            logger.error(
                "statefulset_restart_failed",
                name=name,
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to restart statefulset {name}: {e.reason}") from e

    def restart_daemonset(self, name: str, namespace: str) -> bool:
        """Restart a daemonset using rollout restart strategy.

        Args:
            name: DaemonSet name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesError: If restart fails
        """
        try:
            logger.info("restarting_daemonset", name=name, namespace=namespace)

            # Patch daemonset with restart annotation
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
                    }
                }
            }

            self.apps_v1.patch_namespaced_daemon_set(name=name, namespace=namespace, body=body)

            logger.info("daemonset_restart_initiated", name=name, namespace=namespace)
            return True

        except ApiException as e:
            logger.error(
                "daemonset_restart_failed",
                name=name,
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to restart daemonset {name}: {e.reason}") from e

    def get_deployments(self, namespace: str) -> list[V1Deployment]:
        """Get all deployments in a namespace.

        Args:
            namespace: Namespace to query

        Returns:
            List of V1Deployment objects

        Raises:
            KubernetesError: If deployments cannot be retrieved
        """
        try:
            logger.debug("getting_deployments", namespace=namespace)
            response = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            deployments = response.items

            logger.info("deployments_retrieved", namespace=namespace, count=len(deployments))
            return deployments

        except ApiException as e:
            logger.error(
                "get_deployments_failed",
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to get deployments in {namespace}: {e.reason}") from e

    def get_statefulsets(self, namespace: str) -> list[V1StatefulSet]:
        """Get all statefulsets in a namespace.

        Args:
            namespace: Namespace to query

        Returns:
            List of V1StatefulSet objects

        Raises:
            KubernetesError: If statefulsets cannot be retrieved
        """
        try:
            logger.debug("getting_statefulsets", namespace=namespace)
            response = self.apps_v1.list_namespaced_stateful_set(namespace=namespace)
            statefulsets = response.items

            logger.info("statefulsets_retrieved", namespace=namespace, count=len(statefulsets))
            return statefulsets

        except ApiException as e:
            logger.error(
                "get_statefulsets_failed",
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to get statefulsets in {namespace}: {e.reason}") from e

    def get_daemonsets(self, namespace: str) -> list[V1DaemonSet]:
        """Get all daemonsets in a namespace.

        Args:
            namespace: Namespace to query

        Returns:
            List of V1DaemonSet objects

        Raises:
            KubernetesError: If daemonsets cannot be retrieved
        """
        try:
            logger.debug("getting_daemonsets", namespace=namespace)
            response = self.apps_v1.list_namespaced_daemon_set(namespace=namespace)
            daemonsets = response.items

            logger.info("daemonsets_retrieved", namespace=namespace, count=len(daemonsets))
            return daemonsets

        except ApiException as e:
            logger.error(
                "get_daemonsets_failed",
                namespace=namespace,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to get daemonsets in {namespace}: {e.reason}") from e

    def exec_in_pod(
        self,
        namespace: str,
        pod_name: str,
        command: list[str],
        container: str | None = None,
    ) -> dict[str, str]:
        """Execute a command in a pod.

        Args:
            namespace: Namespace
            pod_name: Pod name
            command: Command to execute as a list (e.g., ["sh", "-c", "echo hello"])
            container: Container name (optional, uses first container if not specified)

        Returns:
            Dictionary with 'stdout' and 'stderr' keys

        Raises:
            KubernetesError: If execution fails
        """
        try:
            logger.debug(
                "exec_in_pod",
                namespace=namespace,
                pod_name=pod_name,
                command=command,
                container=container,
            )

            # Execute command using Kubernetes stream API
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=command,
                container=container,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False,
            )

            # Read output
            stdout_lines = []
            stderr_lines = []

            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout_lines.append(resp.read_stdout())
                if resp.peek_stderr():
                    stderr_lines.append(resp.read_stderr())

            resp.close()

            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)

            logger.info(
                "exec_in_pod_completed",
                namespace=namespace,
                pod_name=pod_name,
                stdout_len=len(stdout),
                stderr_len=len(stderr),
            )

            return {"stdout": stdout, "stderr": stderr}

        except ApiException as e:
            logger.error(
                "exec_in_pod_failed",
                namespace=namespace,
                pod_name=pod_name,
                status=e.status,
                reason=e.reason,
            )
            raise KubernetesError(f"Failed to exec in pod {pod_name}: {e.reason}") from e
        except Exception as e:
            logger.error(
                "exec_in_pod_unexpected_error",
                namespace=namespace,
                pod_name=pod_name,
                error=str(e),
            )
            raise KubernetesError(f"Unexpected error executing in pod {pod_name}: {e}") from e
