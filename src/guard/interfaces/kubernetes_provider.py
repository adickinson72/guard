"""Kubernetes provider interface for cluster operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NodeInfo:
    """Normalized node information."""

    name: str
    ready: bool
    conditions: dict[str, str]
    capacity: dict[str, str]
    allocatable: dict[str, str]


@dataclass
class PodInfo:
    """Normalized pod information."""

    name: str
    namespace: str
    ready: bool
    phase: str
    conditions: dict[str, str]
    container_statuses: list[dict[str, any]]


@dataclass
class DeploymentInfo:
    """Normalized deployment information."""

    name: str
    namespace: str
    ready: bool
    replicas_desired: int
    replicas_ready: int
    replicas_available: int
    replicas_updated: int


class KubernetesProvider(ABC):
    """Abstract interface for Kubernetes operations.

    This interface provides cluster-agnostic access to Kubernetes resources,
    hiding implementation details of the kubernetes Python client.

    All methods return normalized data structures (dataclasses) rather than
    native K8s API objects to maintain clean black box boundaries.
    """

    @abstractmethod
    async def get_nodes(self) -> list[NodeInfo]:
        """Get all nodes in the cluster.

        Returns:
            List of normalized node information

        Raises:
            KubernetesProviderError: If nodes cannot be retrieved
        """

    @abstractmethod
    async def check_nodes_ready(self) -> tuple[bool, list[str]]:
        """Check if all nodes are ready.

        Returns:
            Tuple of (all_ready, list of unready node names)

        Raises:
            KubernetesProviderError: If check fails
        """

    @abstractmethod
    async def get_pods(self, namespace: str, label_selector: str | None = None) -> list[PodInfo]:
        """Get pods in a namespace.

        Args:
            namespace: Namespace to query
            label_selector: Optional label selector (e.g., "app=istiod")

        Returns:
            List of normalized pod information

        Raises:
            KubernetesProviderError: If pods cannot be retrieved
        """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    async def get_namespaces(self, label_selector: str | None = None) -> list[str]:
        """Get namespace names.

        Args:
            label_selector: Optional label selector

        Returns:
            List of namespace names

        Raises:
            KubernetesProviderError: If namespaces cannot be retrieved
        """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    async def exec_in_pod(
        self, namespace: str, pod_name: str, command: list[str], container: str | None = None
    ) -> dict[str, str]:
        """Execute a command in a pod.

        Args:
            namespace: Namespace
            pod_name: Pod name
            command: Command to execute
            container: Container name (optional)

        Returns:
            Dictionary with stdout and stderr

        Raises:
            KubernetesProviderError: If execution fails
        """
