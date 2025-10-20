"""Kubernetes adapter implementing KubernetesProvider interface."""


from guard.clients.kubernetes_client import KubernetesClient
from guard.interfaces.exceptions import KubernetesProviderError
from guard.interfaces.kubernetes_provider import (
    DeploymentInfo,
    KubernetesProvider,
    NodeInfo,
    PodInfo,
)
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class KubernetesAdapter(KubernetesProvider):
    """Adapter wrapping KubernetesClient to implement KubernetesProvider interface.

    This adapter normalizes Kubernetes API responses into clean dataclasses,
    hiding kubernetes Python client implementation details.
    """

    def __init__(self, kubeconfig_path: str | None = None, context: str | None = None):
        """Initialize Kubernetes adapter.

        Args:
            kubeconfig_path: Path to kubeconfig file (optional)
            context: Kubernetes context to use (optional)
        """
        try:
            self.client = KubernetesClient(kubeconfig_path=kubeconfig_path, context=context)
            logger.debug("k8s_adapter_initialized", context=context)
        except Exception as e:
            raise KubernetesProviderError(f"Failed to initialize K8s adapter: {e}") from e

    async def get_nodes(self) -> list[NodeInfo]:
        """Get all nodes in the cluster.

        Returns:
            List of normalized node information

        Raises:
            KubernetesProviderError: If nodes cannot be retrieved
        """
        try:
            nodes = self.client.get_nodes()

            # Normalize to NodeInfo dataclass
            node_infos = []
            for node in nodes:
                conditions = {}
                if node.status.conditions:
                    conditions = {cond.type: cond.status for cond in node.status.conditions}

                node_info = NodeInfo(
                    name=node.metadata.name,
                    ready=conditions.get("Ready") == "True",
                    conditions=conditions,
                    capacity=dict(node.status.capacity) if node.status.capacity else {},
                    allocatable=dict(node.status.allocatable) if node.status.allocatable else {},
                )
                node_infos.append(node_info)

            return node_infos

        except Exception as e:
            logger.error("get_nodes_failed", error=str(e))
            raise KubernetesProviderError(f"Failed to get nodes: {e}") from e

    async def check_nodes_ready(self) -> tuple[bool, list[str]]:
        """Check if all nodes are ready.

        Returns:
            Tuple of (all_ready, list of unready node names)

        Raises:
            KubernetesProviderError: If check fails
        """
        try:
            return self.client.check_nodes_ready()
        except Exception as e:
            logger.error("check_nodes_ready_failed", error=str(e))
            raise KubernetesProviderError(f"Failed to check nodes ready: {e}") from e

    async def get_pods(self, namespace: str, label_selector: str | None = None) -> list[PodInfo]:
        """Get pods in a namespace.

        Args:
            namespace: Namespace to query
            label_selector: Optional label selector

        Returns:
            List of normalized pod information

        Raises:
            KubernetesProviderError: If pods cannot be retrieved
        """
        try:
            pods = self.client.get_pods(namespace=namespace, label_selector=label_selector)

            # Normalize to PodInfo dataclass
            pod_infos = []
            for pod in pods:
                conditions = {}
                if pod.status.conditions:
                    conditions = {cond.type: cond.status for cond in pod.status.conditions}

                container_statuses = []
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        container_statuses.append(
                            {
                                "name": cs.name,
                                "ready": cs.ready,
                                "restart_count": cs.restart_count,
                                "image": cs.image,
                            }
                        )

                pod_info = PodInfo(
                    name=pod.metadata.name,
                    namespace=pod.metadata.namespace,
                    ready=conditions.get("Ready") == "True",
                    phase=pod.status.phase,
                    conditions=conditions,
                    container_statuses=container_statuses,
                )
                pod_infos.append(pod_info)

            return pod_infos

        except Exception as e:
            logger.error("get_pods_failed", namespace=namespace, error=str(e))
            raise KubernetesProviderError(f"Failed to get pods in {namespace}: {e}") from e

    async def check_pods_ready(
        self, namespace: str, label_selector: str | None = None
    ) -> tuple[bool, list[str]]:
        """Check if all matching pods are ready.

        Args:
            namespace: Namespace to check
            label_selector: Optional label selector

        Returns:
            Tuple of (all_ready, list of unready pod names)

        Raises:
            KubernetesProviderError: If check fails
        """
        try:
            return self.client.check_pods_ready(namespace=namespace, label_selector=label_selector)
        except Exception as e:
            logger.error("check_pods_ready_failed", namespace=namespace, error=str(e))
            raise KubernetesProviderError(f"Failed to check pods ready: {e}") from e

    async def get_deployment(self, name: str, namespace: str) -> DeploymentInfo:
        """Get deployment information.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            Normalized deployment information

        Raises:
            KubernetesProviderError: If deployment cannot be retrieved
        """
        try:
            deployment = self.client.get_deployment(name=name, namespace=namespace)

            # Normalize to DeploymentInfo
            return DeploymentInfo(
                name=deployment.metadata.name,
                namespace=deployment.metadata.namespace,
                ready=self.client.check_deployment_ready(name=name, namespace=namespace),
                replicas_desired=deployment.spec.replicas or 0,
                replicas_ready=deployment.status.ready_replicas or 0,
                replicas_available=deployment.status.available_replicas or 0,
                replicas_updated=deployment.status.updated_replicas or 0,
            )

        except Exception as e:
            logger.error("get_deployment_failed", name=name, namespace=namespace, error=str(e))
            raise KubernetesProviderError(f"Failed to get deployment {name}: {e}") from e

    async def check_deployment_ready(self, name: str, namespace: str) -> bool:
        """Check if a deployment is ready.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            True if deployment is ready

        Raises:
            KubernetesProviderError: If check fails
        """
        try:
            return self.client.check_deployment_ready(name=name, namespace=namespace)
        except Exception as e:
            logger.error(
                "check_deployment_ready_failed",
                name=name,
                namespace=namespace,
                error=str(e),
            )
            raise KubernetesProviderError(f"Failed to check deployment ready: {e}") from e

    async def get_namespaces(self, label_selector: str | None = None) -> list[str]:
        """Get namespace names.

        Args:
            label_selector: Optional label selector

        Returns:
            List of namespace names

        Raises:
            KubernetesProviderError: If namespaces cannot be retrieved
        """
        try:
            namespaces = self.client.get_namespaces(label_selector=label_selector)
            return [ns.metadata.name for ns in namespaces]
        except Exception as e:
            logger.error("get_namespaces_failed", error=str(e))
            raise KubernetesProviderError(f"Failed to get namespaces: {e}") from e

    async def restart_deployment(self, name: str, namespace: str) -> bool:
        """Restart a deployment.

        Args:
            name: Deployment name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesProviderError: If restart fails
        """
        try:
            return self.client.restart_deployment(name=name, namespace=namespace)
        except Exception as e:
            logger.error(
                "restart_deployment_failed",
                name=name,
                namespace=namespace,
                error=str(e),
            )
            raise KubernetesProviderError(f"Failed to restart deployment {name}: {e}") from e

    async def restart_daemonset(self, name: str, namespace: str) -> bool:
        """Restart a daemonset.

        Args:
            name: DaemonSet name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesProviderError: If restart fails
        """
        try:
            return self.client.restart_daemonset(name=name, namespace=namespace)
        except Exception as e:
            logger.error(
                "restart_daemonset_failed",
                name=name,
                namespace=namespace,
                error=str(e),
            )
            raise KubernetesProviderError(f"Failed to restart daemonset {name}: {e}") from e

    async def restart_statefulset(self, name: str, namespace: str) -> bool:
        """Restart a statefulset.

        Args:
            name: StatefulSet name
            namespace: Namespace

        Returns:
            True if restart was initiated successfully

        Raises:
            KubernetesProviderError: If restart fails
        """
        try:
            return self.client.restart_statefulset(name=name, namespace=namespace)
        except Exception as e:
            logger.error(
                "restart_statefulset_failed",
                name=name,
                namespace=namespace,
                error=str(e),
            )
            raise KubernetesProviderError(f"Failed to restart statefulset {name}: {e}") from e

    async def exec_in_pod(
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
            command: Command to execute (list of strings)
            container: Container name (optional)

        Returns:
            Dictionary with stdout and stderr

        Raises:
            KubernetesProviderError: If execution fails
        """
        try:
            logger.debug(
                "exec_in_pod",
                namespace=namespace,
                pod_name=pod_name,
                command=command,
                container=container,
            )

            result = self.client.exec_in_pod(
                namespace=namespace,
                pod_name=pod_name,
                command=command,
                container=container,
            )

            return result

        except Exception as e:
            logger.error(
                "exec_in_pod_failed",
                namespace=namespace,
                pod_name=pod_name,
                error=str(e),
            )
            raise KubernetesProviderError(f"Failed to exec in pod {pod_name}: {e}") from e
