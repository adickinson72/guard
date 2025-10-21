"""Integration tests for Kubernetes client."""

import os
from pathlib import Path

import pytest
from kubernetes.config.config_exception import ConfigException

from guard.clients.kubernetes_client import KubernetesClient
from guard.core.exceptions import KubernetesError


@pytest.mark.integration
class TestKubernetesClientIntegration:
    """Integration tests for KubernetesClient with real Kubernetes cluster."""

    @pytest.fixture
    def skip_if_no_kubeconfig(self):
        """Skip test if kubeconfig is not available."""
        # Check if kubeconfig exists or if we're in-cluster
        kubeconfig_path = os.getenv("KUBECONFIG", Path("~/.kube/config").expanduser())
        if not Path(kubeconfig_path).exists():
            pytest.skip(
                "Kubeconfig not found. Set KUBECONFIG environment variable or "
                "ensure ~/.kube/config exists."
            )

    @pytest.fixture
    def k8s_client(self, skip_if_no_kubeconfig) -> KubernetesClient:
        """Create Kubernetes client for integration tests."""
        context = os.getenv("K8S_TEST_CONTEXT")  # Optional: use specific context
        try:
            return KubernetesClient(context=context)
        except (ConfigException, KubernetesError) as e:
            pytest.skip(f"Failed to initialize Kubernetes client: {e}")

    def test_client_initialization(self, k8s_client: KubernetesClient):
        """Test Kubernetes client initializes successfully."""
        assert k8s_client.core_v1 is not None
        assert k8s_client.apps_v1 is not None
        assert k8s_client.admissionregistration_v1 is not None

    def test_get_nodes(self, k8s_client: KubernetesClient):
        """Test retrieving nodes from cluster."""
        nodes = k8s_client.get_nodes()

        assert isinstance(nodes, list)
        # Most clusters have at least one node
        assert len(nodes) > 0

        # Verify node structure
        node = nodes[0]
        assert hasattr(node, "metadata")
        assert hasattr(node.metadata, "name")
        assert hasattr(node, "status")

    def test_check_nodes_ready(self, k8s_client: KubernetesClient):
        """Test checking node readiness."""
        all_ready, unready_nodes = k8s_client.check_nodes_ready()

        assert isinstance(all_ready, bool)
        assert isinstance(unready_nodes, list)

        # In a healthy cluster, all nodes should be ready
        # But we won't fail the test if some are not ready
        if not all_ready:
            print(f"Warning: {len(unready_nodes)} nodes are not ready: {unready_nodes}")

    def test_list_namespaces(self, k8s_client: KubernetesClient):
        """Test listing namespaces."""
        namespaces = k8s_client.list_namespaces()

        assert isinstance(namespaces, list)
        assert len(namespaces) > 0

        # Check for common namespaces
        namespace_names = [ns.metadata.name for ns in namespaces]
        assert "default" in namespace_names
        assert "kube-system" in namespace_names

    def test_get_pods_default_namespace(self, k8s_client: KubernetesClient):
        """Test retrieving pods from default namespace."""
        pods = k8s_client.get_pods(namespace="default")

        assert isinstance(pods, list)
        # default namespace might be empty, so we just check it's a list

    def test_get_pods_kube_system(self, k8s_client: KubernetesClient):
        """Test retrieving pods from kube-system namespace."""
        pods = k8s_client.get_pods(namespace="kube-system")

        assert isinstance(pods, list)
        # kube-system should have system pods
        assert len(pods) > 0

        # Verify pod structure
        pod = pods[0]
        assert hasattr(pod, "metadata")
        assert hasattr(pod.metadata, "name")
        assert hasattr(pod, "status")

    def test_get_pods_with_label_selector(self, k8s_client: KubernetesClient):
        """Test retrieving pods with label selector."""
        # Try common labels that might exist in kube-system
        label_selectors_to_try = [
            "k8s-app=kube-dns",
            "component=kube-apiserver",
            "k8s-app=kube-proxy",
        ]

        found_pods = False
        for selector in label_selectors_to_try:
            try:
                pods = k8s_client.get_pods(namespace="kube-system", label_selector=selector)
                if len(pods) > 0:
                    found_pods = True
                    assert isinstance(pods, list)
                    # Verify label selector worked
                    pod = pods[0]
                    assert hasattr(pod.metadata, "labels")
                    break
            except KubernetesError:
                continue

        if not found_pods:
            pytest.skip("Could not find pods with common label selectors for testing")

    def test_get_pods_nonexistent_namespace(self, k8s_client: KubernetesClient):
        """Test getting pods from non-existent namespace raises error."""
        with pytest.raises(KubernetesError):
            k8s_client.get_pods(namespace="nonexistent-namespace-12345")

    def test_check_pods_ready_kube_system(self, k8s_client: KubernetesClient):
        """Test checking pod readiness in kube-system."""
        all_ready, unready_pods = k8s_client.check_pods_ready(namespace="kube-system")

        assert isinstance(all_ready, bool)
        assert isinstance(unready_pods, list)

        # In a healthy cluster, kube-system pods should be ready
        if not all_ready:
            print(
                f"Warning: {len(unready_pods)} pods in kube-system are not ready: "
                f"{unready_pods}"
            )

    def test_get_namespaces_with_label(self, k8s_client: KubernetesClient):
        """Test retrieving namespaces with label selector."""
        # Try to get namespaces with istio-injection enabled (if Istio is installed)
        try:
            namespaces = k8s_client.get_namespaces_with_label("istio-injection=enabled")
            assert isinstance(namespaces, list)
        except KubernetesError:
            pytest.skip("Istio not installed or no namespaces with istio-injection label")


@pytest.mark.integration
class TestKubernetesClientIstioIntegration:
    """Integration tests for Istio-specific Kubernetes operations."""

    @pytest.fixture
    def skip_if_no_kubeconfig(self):
        """Skip test if kubeconfig is not available."""
        kubeconfig_path = os.getenv("KUBECONFIG", Path("~/.kube/config").expanduser())
        if not Path(kubeconfig_path).exists():
            pytest.skip("Kubeconfig not found")

    @pytest.fixture
    def k8s_client(self, skip_if_no_kubeconfig) -> KubernetesClient:
        """Create Kubernetes client for integration tests."""
        try:
            return KubernetesClient()
        except (ConfigException, KubernetesError) as e:
            pytest.skip(f"Failed to initialize Kubernetes client: {e}")

    @pytest.fixture
    def skip_if_no_istio(self, k8s_client: KubernetesClient):
        """Skip test if Istio is not installed in the cluster."""
        try:
            namespaces = k8s_client.list_namespaces()
            namespace_names = [ns.metadata.name for ns in namespaces]
            if "istio-system" not in namespace_names:
                pytest.skip("Istio not installed in cluster (istio-system namespace not found)")
        except Exception as e:
            pytest.skip(f"Failed to check for Istio installation: {e}")

    def test_get_istio_pods(self, k8s_client: KubernetesClient, skip_if_no_istio):
        """Test retrieving Istio control plane pods."""
        pods = k8s_client.get_pods(namespace="istio-system", label_selector="app=istiod")

        assert isinstance(pods, list)
        if len(pods) > 0:
            pod = pods[0]
            assert hasattr(pod.metadata, "name")
            assert "istiod" in pod.metadata.name

    def test_check_istio_pods_ready(self, k8s_client: KubernetesClient, skip_if_no_istio):
        """Test checking Istio pod readiness."""
        all_ready, unready_pods = k8s_client.check_pods_ready(
            namespace="istio-system", label_selector="app=istiod"
        )

        assert isinstance(all_ready, bool)
        assert isinstance(unready_pods, list)

        # Istio pods should be ready in a healthy cluster
        if not all_ready:
            print(f"Warning: {len(unready_pods)} Istio pods are not ready: {unready_pods}")

    def test_get_namespaces_with_istio_injection(
        self, k8s_client: KubernetesClient, skip_if_no_istio
    ):
        """Test getting namespaces with Istio sidecar injection enabled."""
        namespaces = k8s_client.get_namespaces_with_label("istio-injection=enabled")

        assert isinstance(namespaces, list)
        # May be empty if no namespaces have injection enabled


@pytest.mark.integration
@pytest.mark.slow
class TestKubernetesClientDeploymentOperations:
    """Integration tests for deployment operations.

    These are marked as slow since they may take time in large clusters.
    """

    @pytest.fixture
    def k8s_client(self) -> KubernetesClient:
        """Create Kubernetes client for integration tests."""
        try:
            return KubernetesClient()
        except (ConfigException, KubernetesError) as e:
            pytest.skip(f"Failed to initialize Kubernetes client: {e}")

    def test_get_deployments(self, k8s_client: KubernetesClient):
        """Test retrieving deployments from kube-system."""
        deployments = k8s_client.get_deployments(namespace="kube-system")

        assert isinstance(deployments, list)
        # kube-system typically has deployments
        if len(deployments) > 0:
            deployment = deployments[0]
            assert hasattr(deployment, "metadata")
            assert hasattr(deployment.metadata, "name")

    def test_get_statefulsets(self, k8s_client: KubernetesClient):
        """Test retrieving statefulsets."""
        # Try a few common namespaces
        for namespace in ["kube-system", "default"]:
            try:
                statefulsets = k8s_client.get_statefulsets(namespace=namespace)
                assert isinstance(statefulsets, list)
            except KubernetesError:
                continue

    def test_get_daemonsets(self, k8s_client: KubernetesClient):
        """Test retrieving daemonsets from kube-system."""
        daemonsets = k8s_client.get_daemonsets(namespace="kube-system")

        assert isinstance(daemonsets, list)
        # kube-system typically has daemonsets (kube-proxy, etc.)
        if len(daemonsets) > 0:
            daemonset = daemonsets[0]
            assert hasattr(daemonset, "metadata")
            assert hasattr(daemonset.metadata, "name")
