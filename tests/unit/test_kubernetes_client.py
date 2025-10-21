"""Unit tests for Kubernetes client.

This module tests the KubernetesClient wrapper for Kubernetes API operations including:
- Node management and health checks
- Pod management and readiness checks
- Deployment/StatefulSet/DaemonSet operations
- Webhook configuration retrieval
- Namespace management
- Resource restart operations
- Pod command execution
"""

from unittest.mock import Mock, patch

import pytest
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1DaemonSet,
    V1DaemonSetSpec,
    V1DaemonSetStatus,
    V1Deployment,
    V1DeploymentStatus,
    V1LabelSelector,
    V1Namespace,
    V1Node,
    V1NodeCondition,
    V1NodeStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodCondition,
    V1PodStatus,
    V1PodTemplateSpec,
    V1StatefulSet,
    V1StatefulSetStatus,
)

from guard.clients.kubernetes_client import KubernetesClient
from guard.core.exceptions import KubernetesError


class TestKubernetesClientInitialization:
    """Tests for KubernetesClient initialization."""

    def test_kubernetes_client_initialization_default(self) -> None:
        """Test KubernetesClient initializes with default kubeconfig."""
        with patch("kubernetes.config.load_kube_config") as mock_load:
            client = KubernetesClient()

            mock_load.assert_called_once_with(context=None)
            assert client.core_v1 is not None
            assert client.apps_v1 is not None

    def test_kubernetes_client_initialization_with_kubeconfig(self) -> None:
        """Test KubernetesClient initializes with custom kubeconfig."""
        with patch("kubernetes.config.load_kube_config") as mock_load:
            KubernetesClient(kubeconfig_path="/path/to/kubeconfig")

            mock_load.assert_called_once_with(config_file="/path/to/kubeconfig", context=None)

    def test_kubernetes_client_initialization_with_context(self) -> None:
        """Test KubernetesClient initializes with specific context."""
        with patch("kubernetes.config.load_kube_config") as mock_load:
            KubernetesClient(context="test-context")

            mock_load.assert_called_once_with(context="test-context")

    def test_kubernetes_client_initialization_in_cluster(self) -> None:
        """Test KubernetesClient falls back to in-cluster config."""
        with patch("kubernetes.config.load_kube_config") as mock_load_kube, patch(
            "kubernetes.config.load_incluster_config"
        ) as mock_load_incluster:
            from kubernetes import config

            mock_load_kube.side_effect = config.ConfigException("Not in cluster")

            KubernetesClient()

            mock_load_kube.assert_called_once()
            mock_load_incluster.assert_called_once()

    def test_kubernetes_client_initialization_failure(self) -> None:
        """Test KubernetesClient raises error on initialization failure."""
        with patch("kubernetes.config.load_kube_config") as mock_load_kube, patch(
            "kubernetes.config.load_incluster_config"
        ) as mock_load_incluster:
            from kubernetes import config

            mock_load_kube.side_effect = config.ConfigException("Config error")
            mock_load_incluster.side_effect = config.ConfigException("Not in cluster")

            with pytest.raises(KubernetesError) as exc_info:
                KubernetesClient()

            assert "Failed to initialize Kubernetes client" in str(exc_info.value)


class TestGetNodes:
    """Tests for get_nodes method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_nodes_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful node retrieval."""
        mock_node1 = V1Node(metadata=V1ObjectMeta(name="node-1"))
        mock_node2 = V1Node(metadata=V1ObjectMeta(name="node-2"))

        mock_response = Mock()
        mock_response.items = [mock_node1, mock_node2]

        k8s_client.core_v1.list_node = Mock(return_value=mock_response)

        result = k8s_client.get_nodes()

        assert len(result) == 2
        assert result[0].metadata.name == "node-1"
        assert result[1].metadata.name == "node-2"

    def test_get_nodes_api_exception(self, k8s_client: KubernetesClient) -> None:
        """Test get_nodes raises KubernetesError on API exception."""
        k8s_client.core_v1.list_node = Mock(
            side_effect=ApiException(status=403, reason="Forbidden")
        )

        with pytest.raises(KubernetesError) as exc_info:
            k8s_client.get_nodes()

        assert "Failed to get nodes" in str(exc_info.value)


class TestCheckNodesReady:
    """Tests for check_nodes_ready method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_check_nodes_ready_all_ready(self, k8s_client: KubernetesClient) -> None:
        """Test check_nodes_ready returns True when all nodes ready."""
        mock_node1 = V1Node(
            metadata=V1ObjectMeta(name="node-1"),
            status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="True")]),
        )
        mock_node2 = V1Node(
            metadata=V1ObjectMeta(name="node-2"),
            status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="True")]),
        )

        mock_response = Mock()
        mock_response.items = [mock_node1, mock_node2]
        k8s_client.core_v1.list_node = Mock(return_value=mock_response)

        all_ready, unready_nodes = k8s_client.check_nodes_ready()

        assert all_ready is True
        assert unready_nodes == []

    def test_check_nodes_ready_some_unready(self, k8s_client: KubernetesClient) -> None:
        """Test check_nodes_ready detects unready nodes."""
        mock_node1 = V1Node(
            metadata=V1ObjectMeta(name="node-1"),
            status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="True")]),
        )
        mock_node2 = V1Node(
            metadata=V1ObjectMeta(name="node-2"),
            status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="False")]),
        )
        mock_node3 = V1Node(
            metadata=V1ObjectMeta(name="node-3"),
            status=V1NodeStatus(conditions=[V1NodeCondition(type="Ready", status="Unknown")]),
        )

        mock_response = Mock()
        mock_response.items = [mock_node1, mock_node2, mock_node3]
        k8s_client.core_v1.list_node = Mock(return_value=mock_response)

        all_ready, unready_nodes = k8s_client.check_nodes_ready()

        assert all_ready is False
        assert len(unready_nodes) == 2
        assert "node-2" in unready_nodes
        assert "node-3" in unready_nodes


class TestGetPods:
    """Tests for get_pods method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_pods_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful pod retrieval."""
        mock_pod1 = V1Pod(metadata=V1ObjectMeta(name="pod-1"))
        mock_pod2 = V1Pod(metadata=V1ObjectMeta(name="pod-2"))

        mock_response = Mock()
        mock_response.items = [mock_pod1, mock_pod2]

        k8s_client.core_v1.list_namespaced_pod = Mock(return_value=mock_response)

        result = k8s_client.get_pods(namespace="default")

        assert len(result) == 2
        k8s_client.core_v1.list_namespaced_pod.assert_called_once_with(
            namespace="default", label_selector=None
        )

    def test_get_pods_with_label_selector(self, k8s_client: KubernetesClient) -> None:
        """Test pod retrieval with label selector."""
        mock_response = Mock()
        mock_response.items = []

        k8s_client.core_v1.list_namespaced_pod = Mock(return_value=mock_response)

        k8s_client.get_pods(namespace="istio-system", label_selector="app=istiod")

        k8s_client.core_v1.list_namespaced_pod.assert_called_once_with(
            namespace="istio-system", label_selector="app=istiod"
        )


class TestCheckPodsReady:
    """Tests for check_pods_ready method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_check_pods_ready_all_ready(self, k8s_client: KubernetesClient) -> None:
        """Test check_pods_ready returns True when all pods ready."""
        mock_pod1 = V1Pod(
            metadata=V1ObjectMeta(name="pod-1"),
            status=V1PodStatus(conditions=[V1PodCondition(type="Ready", status="True")]),
        )
        mock_pod2 = V1Pod(
            metadata=V1ObjectMeta(name="pod-2"),
            status=V1PodStatus(conditions=[V1PodCondition(type="Ready", status="True")]),
        )

        mock_response = Mock()
        mock_response.items = [mock_pod1, mock_pod2]
        k8s_client.core_v1.list_namespaced_pod = Mock(return_value=mock_response)

        all_ready, unready_pods = k8s_client.check_pods_ready(namespace="default")

        assert all_ready is True
        assert unready_pods == []

    def test_check_pods_ready_some_unready(self, k8s_client: KubernetesClient) -> None:
        """Test check_pods_ready detects unready pods."""
        mock_pod1 = V1Pod(
            metadata=V1ObjectMeta(name="pod-1"),
            status=V1PodStatus(conditions=[V1PodCondition(type="Ready", status="True")]),
        )
        mock_pod2 = V1Pod(
            metadata=V1ObjectMeta(name="pod-2"),
            status=V1PodStatus(conditions=[V1PodCondition(type="Ready", status="False")]),
        )

        mock_response = Mock()
        mock_response.items = [mock_pod1, mock_pod2]
        k8s_client.core_v1.list_namespaced_pod = Mock(return_value=mock_response)

        all_ready, unready_pods = k8s_client.check_pods_ready(namespace="default")

        assert all_ready is False
        assert len(unready_pods) == 1
        assert "pod-2" in unready_pods


class TestGetDeployment:
    """Tests for get_deployment method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_deployment_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful deployment retrieval."""
        mock_deployment = V1Deployment(metadata=V1ObjectMeta(name="test-deployment"))

        k8s_client.apps_v1.read_namespaced_deployment = Mock(return_value=mock_deployment)

        result = k8s_client.get_deployment(name="test-deployment", namespace="default")

        assert result.metadata.name == "test-deployment"

    def test_get_deployment_not_found(self, k8s_client: KubernetesClient) -> None:
        """Test get_deployment raises error when deployment not found."""
        k8s_client.apps_v1.read_namespaced_deployment = Mock(
            side_effect=ApiException(status=404, reason="Not Found")
        )

        with pytest.raises(KubernetesError) as exc_info:
            k8s_client.get_deployment(name="nonexistent", namespace="default")

        assert "not found" in str(exc_info.value)


class TestCheckDeploymentReady:
    """Tests for check_deployment_ready method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_check_deployment_ready_success(self, k8s_client: KubernetesClient) -> None:
        """Test deployment is ready when all conditions met."""
        from datetime import datetime

        from kubernetes.client.models import V1Condition, V1DeploymentSpec

        mock_deployment = V1Deployment(
            metadata=V1ObjectMeta(name="test-deployment", generation=5),
            spec=V1DeploymentSpec(
                replicas=3,
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1DeploymentStatus(
                observed_generation=5,
                replicas=3,
                ready_replicas=3,
                updated_replicas=3,
                available_replicas=3,
                conditions=[
                    V1Condition(
                        type="Available",
                        status="True",
                        last_transition_time=datetime.now(),
                        message="Deployment is available",
                        reason="MinimumReplicasAvailable",
                    )
                ],
            ),
        )

        k8s_client.apps_v1.read_namespaced_deployment = Mock(return_value=mock_deployment)

        result = k8s_client.check_deployment_ready(name="test-deployment", namespace="default")

        assert result is True

    def test_check_deployment_ready_replicas_not_ready(self, k8s_client: KubernetesClient) -> None:
        """Test deployment not ready when replicas not updated."""
        from datetime import datetime

        from kubernetes.client.models import V1Condition, V1DeploymentSpec

        mock_deployment = V1Deployment(
            metadata=V1ObjectMeta(name="test-deployment", generation=5),
            spec=V1DeploymentSpec(
                replicas=3,
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1DeploymentStatus(
                observed_generation=5,
                replicas=3,
                ready_replicas=2,
                updated_replicas=2,
                available_replicas=2,
                conditions=[
                    V1Condition(
                        type="Available",
                        status="True",
                        last_transition_time=datetime.now(),
                        message="Deployment is available",
                        reason="MinimumReplicasAvailable",
                    )
                ],
            ),
        )

        k8s_client.apps_v1.read_namespaced_deployment = Mock(return_value=mock_deployment)

        result = k8s_client.check_deployment_ready(name="test-deployment", namespace="default")

        assert result is False

    def test_check_deployment_ready_generation_mismatch(self, k8s_client: KubernetesClient) -> None:
        """Test deployment not ready when generation mismatch."""
        from datetime import datetime

        from kubernetes.client.models import V1Condition, V1DeploymentSpec

        mock_deployment = V1Deployment(
            metadata=V1ObjectMeta(name="test-deployment", generation=5),
            spec=V1DeploymentSpec(
                replicas=3,
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1DeploymentStatus(
                observed_generation=4,
                replicas=3,
                ready_replicas=3,
                updated_replicas=3,
                available_replicas=3,
                conditions=[
                    V1Condition(
                        type="Available",
                        status="True",
                        last_transition_time=datetime.now(),
                        message="Deployment is available",
                        reason="MinimumReplicasAvailable",
                    )
                ],
            ),
        )

        k8s_client.apps_v1.read_namespaced_deployment = Mock(return_value=mock_deployment)

        result = k8s_client.check_deployment_ready(name="test-deployment", namespace="default")

        assert result is False


class TestRestartDeployment:
    """Tests for restart_deployment method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_restart_deployment_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful deployment restart."""
        k8s_client.apps_v1.patch_namespaced_deployment = Mock()

        result = k8s_client.restart_deployment(name="test-deployment", namespace="default")

        assert result is True

        # Verify patch was called with restart annotation
        call_args = k8s_client.apps_v1.patch_namespaced_deployment.call_args
        body = call_args[1]["body"]
        assert (
            "kubectl.kubernetes.io/restartedAt"
            in body["spec"]["template"]["metadata"]["annotations"]
        )

    def test_restart_deployment_failure(self, k8s_client: KubernetesClient) -> None:
        """Test restart_deployment raises error on failure."""
        k8s_client.apps_v1.patch_namespaced_deployment = Mock(
            side_effect=ApiException(status=403, reason="Forbidden")
        )

        with pytest.raises(KubernetesError) as exc_info:
            k8s_client.restart_deployment(name="test-deployment", namespace="default")

        assert "Failed to restart deployment" in str(exc_info.value)


class TestRestartStatefulSet:
    """Tests for restart_statefulset method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_restart_statefulset_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful statefulset restart."""
        k8s_client.apps_v1.patch_namespaced_stateful_set = Mock()

        result = k8s_client.restart_statefulset(name="test-sts", namespace="default")

        assert result is True
        k8s_client.apps_v1.patch_namespaced_stateful_set.assert_called_once()


class TestRestartDaemonSet:
    """Tests for restart_daemonset method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_restart_daemonset_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful daemonset restart."""
        k8s_client.apps_v1.patch_namespaced_daemon_set = Mock()

        result = k8s_client.restart_daemonset(name="test-ds", namespace="default")

        assert result is True
        k8s_client.apps_v1.patch_namespaced_daemon_set.assert_called_once()


class TestGetNamespaces:
    """Tests for get_namespaces method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_namespaces_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful namespace retrieval."""
        mock_ns1 = V1Namespace(metadata=V1ObjectMeta(name="default"))
        mock_ns2 = V1Namespace(metadata=V1ObjectMeta(name="kube-system"))

        mock_response = Mock()
        mock_response.items = [mock_ns1, mock_ns2]

        k8s_client.core_v1.list_namespace = Mock(return_value=mock_response)

        result = k8s_client.get_namespaces()

        assert len(result) == 2
        assert result[0].metadata.name == "default"

    def test_get_namespaces_with_label_selector(self, k8s_client: KubernetesClient) -> None:
        """Test namespace retrieval with label selector."""
        mock_response = Mock()
        mock_response.items = []

        k8s_client.core_v1.list_namespace = Mock(return_value=mock_response)

        k8s_client.get_namespaces(label_selector="istio-injection=enabled")

        k8s_client.core_v1.list_namespace.assert_called_once_with(
            label_selector="istio-injection=enabled"
        )


class TestCheckStatefulSetReady:
    """Tests for check_statefulset_ready method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_check_statefulset_ready_success(self, k8s_client: KubernetesClient) -> None:
        """Test statefulset is ready when all conditions met."""
        from kubernetes.client.models import V1StatefulSetSpec

        mock_sts = V1StatefulSet(
            metadata=V1ObjectMeta(name="test-sts"),
            spec=V1StatefulSetSpec(
                replicas=3,
                selector=V1LabelSelector(match_labels={"app": "test"}),
                service_name="test-svc",
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1StatefulSetStatus(
                replicas=3,
                ready_replicas=3,
                current_replicas=3,
                updated_replicas=3,
                current_revision="rev-123",
                update_revision="rev-123",
            ),
        )

        k8s_client.apps_v1.read_namespaced_stateful_set = Mock(return_value=mock_sts)

        result = k8s_client.check_statefulset_ready(name="test-sts", namespace="default")

        assert result is True

    def test_check_statefulset_ready_not_ready(self, k8s_client: KubernetesClient) -> None:
        """Test statefulset not ready when replicas not ready."""
        from kubernetes.client.models import V1StatefulSetSpec

        mock_sts = V1StatefulSet(
            metadata=V1ObjectMeta(name="test-sts"),
            spec=V1StatefulSetSpec(
                replicas=3,
                selector=V1LabelSelector(match_labels={"app": "test"}),
                service_name="test-svc",
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1StatefulSetStatus(
                replicas=3,
                ready_replicas=2,
                current_replicas=2,
                updated_replicas=2,
                current_revision="rev-123",
                update_revision="rev-123",
            ),
        )

        k8s_client.apps_v1.read_namespaced_stateful_set = Mock(return_value=mock_sts)

        result = k8s_client.check_statefulset_ready(name="test-sts", namespace="default")

        assert result is False


class TestCheckDaemonSetReady:
    """Tests for check_daemonset_ready method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_check_daemonset_ready_success(self, k8s_client: KubernetesClient) -> None:
        """Test daemonset is ready when all conditions met."""
        mock_ds = V1DaemonSet(
            metadata=V1ObjectMeta(name="test-ds"),
            spec=V1DaemonSetSpec(
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1DaemonSetStatus(
                current_number_scheduled=5,
                desired_number_scheduled=5,
                number_ready=5,
                updated_number_scheduled=5,
                number_available=5,
                number_misscheduled=0,
            ),
        )

        k8s_client.apps_v1.read_namespaced_daemon_set = Mock(return_value=mock_ds)

        result = k8s_client.check_daemonset_ready(name="test-ds", namespace="default")

        assert result is True

    def test_check_daemonset_ready_not_ready(self, k8s_client: KubernetesClient) -> None:
        """Test daemonset not ready when pods not ready."""
        mock_ds = V1DaemonSet(
            metadata=V1ObjectMeta(name="test-ds"),
            spec=V1DaemonSetSpec(
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": "test"})),
            ),
            status=V1DaemonSetStatus(
                current_number_scheduled=3,
                desired_number_scheduled=5,
                number_ready=3,
                updated_number_scheduled=3,
                number_available=3,
                number_misscheduled=0,
            ),
        )

        k8s_client.apps_v1.read_namespaced_daemon_set = Mock(return_value=mock_ds)

        result = k8s_client.check_daemonset_ready(name="test-ds", namespace="default")

        assert result is False


class TestExecInPod:
    """Tests for exec_in_pod method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_exec_in_pod_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful command execution in pod."""
        mock_stream = Mock()
        mock_stream.is_open.side_effect = [True, False]
        mock_stream.peek_stdout.return_value = True
        mock_stream.read_stdout.return_value = "command output"
        mock_stream.peek_stderr.return_value = False
        mock_stream.read_stderr.return_value = ""

        with patch("guard.clients.kubernetes_client.stream", return_value=mock_stream):
            result = k8s_client.exec_in_pod(
                namespace="default",
                pod_name="test-pod",
                command=["echo", "hello"],
            )

            assert "stdout" in result
            assert "stderr" in result
            assert "command output" in result["stdout"]

    def test_exec_in_pod_with_container(self, k8s_client: KubernetesClient) -> None:
        """Test command execution specifies container."""
        mock_stream = Mock()
        mock_stream.is_open.side_effect = [True, False]
        mock_stream.peek_stdout.return_value = False
        mock_stream.read_stdout.return_value = ""
        mock_stream.peek_stderr.return_value = False
        mock_stream.read_stderr.return_value = ""

        with patch(
            "guard.clients.kubernetes_client.stream", return_value=mock_stream
        ) as mock_stream_func:
            k8s_client.exec_in_pod(
                namespace="default",
                pod_name="test-pod",
                command=["ls"],
                container="app-container",
            )

            call_args = mock_stream_func.call_args
            assert call_args[1]["container"] == "app-container"

    def test_exec_in_pod_api_exception(self, k8s_client: KubernetesClient) -> None:
        """Test exec_in_pod raises KubernetesError on API exception."""
        with patch("guard.clients.kubernetes_client.stream") as mock_stream:
            mock_stream.side_effect = ApiException(status=404, reason="Pod not found")

            with pytest.raises(KubernetesError) as exc_info:
                k8s_client.exec_in_pod(
                    namespace="default",
                    pod_name="nonexistent-pod",
                    command=["ls"],
                )

            assert "Failed to exec in pod" in str(exc_info.value)


class TestGetWebhookConfigurations:
    """Tests for webhook configuration retrieval."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_validating_webhook_configurations(self, k8s_client: KubernetesClient) -> None:
        """Test validating webhook configuration retrieval."""
        mock_response = Mock()
        mock_response.items = [Mock(), Mock()]

        k8s_client.admissionregistration_v1.list_validating_webhook_configuration = Mock(
            return_value=mock_response
        )

        result = k8s_client.get_validating_webhook_configurations()

        assert len(result) == 2

    def test_get_mutating_webhook_configurations(self, k8s_client: KubernetesClient) -> None:
        """Test mutating webhook configuration retrieval."""
        mock_response = Mock()
        mock_response.items = [Mock()]

        k8s_client.admissionregistration_v1.list_mutating_webhook_configuration = Mock(
            return_value=mock_response
        )

        result = k8s_client.get_mutating_webhook_configurations()

        assert len(result) == 1


class TestGetDeployments:
    """Tests for get_deployments method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_deployments_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful deployments retrieval."""
        mock_response = Mock()
        mock_response.items = [Mock(), Mock(), Mock()]

        k8s_client.apps_v1.list_namespaced_deployment = Mock(return_value=mock_response)

        result = k8s_client.get_deployments(namespace="default")

        assert len(result) == 3


class TestGetStatefulSets:
    """Tests for get_statefulsets method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_statefulsets_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful statefulsets retrieval."""
        mock_response = Mock()
        mock_response.items = [Mock(), Mock()]

        k8s_client.apps_v1.list_namespaced_stateful_set = Mock(return_value=mock_response)

        result = k8s_client.get_statefulsets(namespace="default")

        assert len(result) == 2


class TestGetDaemonSets:
    """Tests for get_daemonsets method."""

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create KubernetesClient with mocked config."""
        with patch("kubernetes.config.load_kube_config"):
            return KubernetesClient()

    def test_get_daemonsets_success(self, k8s_client: KubernetesClient) -> None:
        """Test successful daemonsets retrieval."""
        mock_response = Mock()
        mock_response.items = [Mock()]

        k8s_client.apps_v1.list_namespaced_daemon_set = Mock(return_value=mock_response)

        result = k8s_client.get_daemonsets(namespace="kube-system")

        assert len(result) == 1
