"""Unit tests for KubernetesAdapter.

Tests the Kubernetes adapter implementation of KubernetesProvider interface.
All Kubernetes API calls are mocked to ensure tests are isolated and fast.
"""

from unittest.mock import MagicMock, patch

import pytest

from guard.adapters.k8s_adapter import KubernetesAdapter
from guard.interfaces.exceptions import KubernetesProviderError
from guard.interfaces.kubernetes_provider import DeploymentInfo, NodeInfo, PodInfo


class TestKubernetesAdapterInit:
    """Tests for KubernetesAdapter initialization."""

    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    def test_init_with_defaults(self, mock_k8s_client_class: MagicMock) -> None:
        """Test initializing adapter with default parameters."""
        mock_client = MagicMock()
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        mock_k8s_client_class.assert_called_once_with(kubeconfig_path=None, context=None)
        assert adapter.client == mock_client

    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    def test_init_with_custom_kubeconfig(self, mock_k8s_client_class: MagicMock) -> None:
        """Test initializing adapter with custom kubeconfig."""
        mock_client = MagicMock()
        mock_k8s_client_class.return_value = mock_client

        KubernetesAdapter(kubeconfig_path="/home/user/.kube/config", context="production")

        mock_k8s_client_class.assert_called_once_with(
            kubeconfig_path="/home/user/.kube/config", context="production"
        )

    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    def test_init_failure_raises_kubernetes_provider_error(
        self, mock_k8s_client_class: MagicMock
    ) -> None:
        """Test initialization failure raises KubernetesProviderError."""
        mock_k8s_client_class.side_effect = Exception("Invalid kubeconfig")

        with pytest.raises(KubernetesProviderError) as exc_info:
            KubernetesAdapter(kubeconfig_path="/invalid/path")

        assert "Failed to initialize K8s adapter" in str(exc_info.value)


class TestKubernetesAdapterGetNodes:
    """Tests for get_nodes method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_nodes_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful node retrieval."""
        mock_client = MagicMock()

        # Mock K8s node objects
        mock_node1 = MagicMock()
        mock_node1.metadata.name = "node-1"
        mock_node1.status.conditions = [
            MagicMock(type="Ready", status="True"),
            MagicMock(type="MemoryPressure", status="False"),
        ]
        mock_node1.status.capacity = {"cpu": "4", "memory": "16Gi"}
        mock_node1.status.allocatable = {"cpu": "3.5", "memory": "14Gi"}

        mock_node2 = MagicMock()
        mock_node2.metadata.name = "node-2"
        mock_node2.status.conditions = [MagicMock(type="Ready", status="True")]
        mock_node2.status.capacity = {"cpu": "8", "memory": "32Gi"}
        mock_node2.status.allocatable = {"cpu": "7.5", "memory": "30Gi"}

        mock_client.get_nodes.return_value = [mock_node1, mock_node2]
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_nodes()

        assert len(result) == 2
        assert all(isinstance(n, NodeInfo) for n in result)
        assert result[0].name == "node-1"
        assert result[0].ready is True
        assert result[0].capacity["cpu"] == "4"
        assert result[1].name == "node-2"

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_nodes_not_ready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test getting nodes when some are not ready."""
        mock_client = MagicMock()

        mock_node = MagicMock()
        mock_node.metadata.name = "unhealthy-node"
        mock_node.status.conditions = [MagicMock(type="Ready", status="False")]
        mock_node.status.capacity = {"cpu": "4", "memory": "16Gi"}
        mock_node.status.allocatable = {"cpu": "3.5", "memory": "14Gi"}

        mock_client.get_nodes.return_value = [mock_node]
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_nodes()

        assert len(result) == 1
        assert result[0].ready is False

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_nodes_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test get_nodes failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.get_nodes.side_effect = Exception("API error")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.get_nodes()

        assert "Failed to get nodes" in str(exc_info.value)


class TestKubernetesAdapterCheckNodesReady:
    """Tests for check_nodes_ready method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_nodes_ready_all_ready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_nodes_ready when all nodes are ready."""
        mock_client = MagicMock()
        mock_client.check_nodes_ready.return_value = (True, [])
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        all_ready, unready = await adapter.check_nodes_ready()

        assert all_ready is True
        assert unready == []

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_nodes_ready_some_unready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_nodes_ready when some nodes are not ready."""
        mock_client = MagicMock()
        mock_client.check_nodes_ready.return_value = (False, ["node-3", "node-5"])
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        all_ready, unready = await adapter.check_nodes_ready()

        assert all_ready is False
        assert len(unready) == 2
        assert "node-3" in unready

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_nodes_ready_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_nodes_ready failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.check_nodes_ready.side_effect = Exception("API error")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.check_nodes_ready()

        assert "Failed to check nodes ready" in str(exc_info.value)


class TestKubernetesAdapterGetPods:
    """Tests for get_pods method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_pods_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful pod retrieval."""
        mock_client = MagicMock()

        # Mock K8s pod objects
        mock_pod = MagicMock()
        mock_pod.metadata.name = "istiod-12345-abcde"
        mock_pod.metadata.namespace = "istio-system"
        mock_pod.status.phase = "Running"
        mock_pod.status.conditions = [MagicMock(type="Ready", status="True")]

        mock_container_status = MagicMock()
        mock_container_status.name = "discovery"
        mock_container_status.ready = True
        mock_container_status.restart_count = 0
        mock_container_status.image = "istio/pilot:1.20.0"
        mock_pod.status.container_statuses = [mock_container_status]

        mock_client.get_pods.return_value = [mock_pod]
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_pods(namespace="istio-system")

        mock_client.get_pods.assert_called_once_with(namespace="istio-system", label_selector=None)
        assert len(result) == 1
        assert isinstance(result[0], PodInfo)
        assert result[0].name == "istiod-12345-abcde"
        assert result[0].namespace == "istio-system"
        assert result[0].ready is True
        assert result[0].phase == "Running"
        assert len(result[0].container_statuses) == 1

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_pods_with_label_selector(self, mock_k8s_client_class: MagicMock) -> None:
        """Test getting pods with label selector."""
        mock_client = MagicMock()
        mock_client.get_pods.return_value = []
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        await adapter.get_pods(namespace="default", label_selector="app=nginx,version=v1")

        mock_client.get_pods.assert_called_once_with(
            namespace="default", label_selector="app=nginx,version=v1"
        )

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_pods_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test get_pods failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.get_pods.side_effect = Exception("Namespace not found")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.get_pods(namespace="nonexistent")

        assert "Failed to get pods in nonexistent" in str(exc_info.value)


class TestKubernetesAdapterCheckPodsReady:
    """Tests for check_pods_ready method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_pods_ready_all_ready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_pods_ready when all pods are ready."""
        mock_client = MagicMock()
        mock_client.check_pods_ready.return_value = (True, [])
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        all_ready, unready = await adapter.check_pods_ready(namespace="default")

        mock_client.check_pods_ready.assert_called_once_with(
            namespace="default", label_selector=None
        )
        assert all_ready is True
        assert unready == []

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_pods_ready_some_unready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_pods_ready when some pods are not ready."""
        mock_client = MagicMock()
        mock_client.check_pods_ready.return_value = (False, ["pod-1", "pod-2"])
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        all_ready, unready = await adapter.check_pods_ready(
            namespace="istio-system", label_selector="app=istiod"
        )

        assert all_ready is False
        assert len(unready) == 2

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_pods_ready_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_pods_ready failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.check_pods_ready.side_effect = Exception("API error")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.check_pods_ready(namespace="default")

        assert "Failed to check pods ready" in str(exc_info.value)


class TestKubernetesAdapterGetDeployment:
    """Tests for get_deployment method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_deployment_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful deployment retrieval."""
        mock_client = MagicMock()

        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "nginx"
        mock_deployment.metadata.namespace = "default"
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 3
        mock_deployment.status.available_replicas = 3
        mock_deployment.status.updated_replicas = 3

        mock_client.get_deployment.return_value = mock_deployment
        mock_client.check_deployment_ready.return_value = True
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_deployment(name="nginx", namespace="default")

        mock_client.get_deployment.assert_called_once_with(name="nginx", namespace="default")
        assert isinstance(result, DeploymentInfo)
        assert result.name == "nginx"
        assert result.namespace == "default"
        assert result.ready is True
        assert result.replicas_desired == 3
        assert result.replicas_ready == 3

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_deployment_not_ready(self, mock_k8s_client_class: MagicMock) -> None:
        """Test getting deployment that's not ready."""
        mock_client = MagicMock()

        mock_deployment = MagicMock()
        mock_deployment.metadata.name = "nginx"
        mock_deployment.metadata.namespace = "default"
        mock_deployment.spec.replicas = 3
        mock_deployment.status.ready_replicas = 1
        mock_deployment.status.available_replicas = 1
        mock_deployment.status.updated_replicas = 3

        mock_client.get_deployment.return_value = mock_deployment
        mock_client.check_deployment_ready.return_value = False
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_deployment(name="nginx", namespace="default")

        assert result.ready is False
        assert result.replicas_desired == 3
        assert result.replicas_ready == 1

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_deployment_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test get_deployment failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.get_deployment.side_effect = Exception("Deployment not found")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.get_deployment(name="nonexistent", namespace="default")

        assert "Failed to get deployment nonexistent" in str(exc_info.value)


class TestKubernetesAdapterCheckDeploymentReady:
    """Tests for check_deployment_ready method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_deployment_ready_true(self, mock_k8s_client_class: MagicMock) -> None:
        """Test checking deployment that is ready."""
        mock_client = MagicMock()
        mock_client.check_deployment_ready.return_value = True
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.check_deployment_ready(name="nginx", namespace="default")

        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_deployment_ready_false(self, mock_k8s_client_class: MagicMock) -> None:
        """Test checking deployment that is not ready."""
        mock_client = MagicMock()
        mock_client.check_deployment_ready.return_value = False
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.check_deployment_ready(name="nginx", namespace="default")

        assert result is False

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_check_deployment_ready_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test check_deployment_ready failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.check_deployment_ready.side_effect = Exception("API error")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.check_deployment_ready(name="nginx", namespace="default")

        assert "Failed to check deployment ready" in str(exc_info.value)


class TestKubernetesAdapterGetNamespaces:
    """Tests for get_namespaces method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_namespaces_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful namespace retrieval."""
        mock_client = MagicMock()

        mock_ns1 = MagicMock()
        mock_ns1.metadata.name = "default"
        mock_ns2 = MagicMock()
        mock_ns2.metadata.name = "kube-system"
        mock_ns3 = MagicMock()
        mock_ns3.metadata.name = "istio-system"

        mock_client.get_namespaces.return_value = [mock_ns1, mock_ns2, mock_ns3]
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_namespaces()

        assert len(result) == 3
        assert "default" in result
        assert "kube-system" in result
        assert "istio-system" in result

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_namespaces_with_label_selector(
        self, mock_k8s_client_class: MagicMock
    ) -> None:
        """Test getting namespaces with label selector."""
        mock_client = MagicMock()

        mock_ns = MagicMock()
        mock_ns.metadata.name = "istio-enabled-ns"
        mock_client.get_namespaces.return_value = [mock_ns]
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.get_namespaces(label_selector="istio-injection=enabled")

        mock_client.get_namespaces.assert_called_once_with(label_selector="istio-injection=enabled")
        assert len(result) == 1
        assert result[0] == "istio-enabled-ns"

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_get_namespaces_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test get_namespaces failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.get_namespaces.side_effect = Exception("API error")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.get_namespaces()

        assert "Failed to get namespaces" in str(exc_info.value)


class TestKubernetesAdapterRestartDeployment:
    """Tests for restart_deployment method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_deployment_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful deployment restart."""
        mock_client = MagicMock()
        mock_client.restart_deployment.return_value = True
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.restart_deployment(name="nginx", namespace="default")

        mock_client.restart_deployment.assert_called_once_with(name="nginx", namespace="default")
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_deployment_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test restart_deployment failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.restart_deployment.side_effect = Exception("Restart failed")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.restart_deployment(name="nginx", namespace="default")

        assert "Failed to restart deployment nginx" in str(exc_info.value)


class TestKubernetesAdapterRestartDaemonSet:
    """Tests for restart_daemonset method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_daemonset_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful daemonset restart."""
        mock_client = MagicMock()
        mock_client.restart_daemonset.return_value = True
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.restart_daemonset(name="fluentd", namespace="logging")

        mock_client.restart_daemonset.assert_called_once_with(name="fluentd", namespace="logging")
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_daemonset_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test restart_daemonset failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.restart_daemonset.side_effect = Exception("Restart failed")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.restart_daemonset(name="fluentd", namespace="logging")

        assert "Failed to restart daemonset fluentd" in str(exc_info.value)


class TestKubernetesAdapterRestartStatefulSet:
    """Tests for restart_statefulset method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_statefulset_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful statefulset restart."""
        mock_client = MagicMock()
        mock_client.restart_statefulset.return_value = True
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.restart_statefulset(name="redis", namespace="default")

        mock_client.restart_statefulset.assert_called_once_with(name="redis", namespace="default")
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_restart_statefulset_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test restart_statefulset failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.restart_statefulset.side_effect = Exception("Restart failed")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.restart_statefulset(name="redis", namespace="default")

        assert "Failed to restart statefulset redis" in str(exc_info.value)


class TestKubernetesAdapterExecInPod:
    """Tests for exec_in_pod method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_exec_in_pod_success(self, mock_k8s_client_class: MagicMock) -> None:
        """Test successful command execution in pod."""
        mock_client = MagicMock()
        mock_client.exec_in_pod.return_value = {"stdout": "Command output", "stderr": ""}
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        result = await adapter.exec_in_pod(
            namespace="default",
            pod_name="nginx-12345-abcde",
            command=["cat", "/etc/nginx/nginx.conf"],
        )

        mock_client.exec_in_pod.assert_called_once_with(
            namespace="default",
            pod_name="nginx-12345-abcde",
            command=["cat", "/etc/nginx/nginx.conf"],
            container=None,
        )
        assert result["stdout"] == "Command output"
        assert result["stderr"] == ""

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_exec_in_pod_with_container(self, mock_k8s_client_class: MagicMock) -> None:
        """Test command execution in specific container."""
        mock_client = MagicMock()
        mock_client.exec_in_pod.return_value = {"stdout": "test", "stderr": ""}
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        await adapter.exec_in_pod(
            namespace="istio-system",
            pod_name="istiod-12345-abcde",
            command=["istioctl", "version"],
            container="discovery",
        )

        mock_client.exec_in_pod.assert_called_once_with(
            namespace="istio-system",
            pod_name="istiod-12345-abcde",
            command=["istioctl", "version"],
            container="discovery",
        )

    @pytest.mark.asyncio
    @patch("guard.adapters.k8s_adapter.KubernetesClient")
    async def test_exec_in_pod_failure(self, mock_k8s_client_class: MagicMock) -> None:
        """Test exec_in_pod failure raises KubernetesProviderError."""
        mock_client = MagicMock()
        mock_client.exec_in_pod.side_effect = Exception("Pod not found")
        mock_k8s_client_class.return_value = mock_client

        adapter = KubernetesAdapter()

        with pytest.raises(KubernetesProviderError) as exc_info:
            await adapter.exec_in_pod(
                namespace="default", pod_name="nonexistent-pod", command=["ls"]
            )

        assert "Failed to exec in pod nonexistent-pod" in str(exc_info.value)
