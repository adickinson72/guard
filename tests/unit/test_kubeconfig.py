"""Tests for kubeconfig management utilities."""

import tempfile
from pathlib import Path

import pytest
import yaml

from guard.utils.kubeconfig import KubeconfigManager


@pytest.fixture
def temp_kubeconfig_path():
    """Create a temporary kubeconfig file path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def kubeconfig_manager(temp_kubeconfig_path):
    """Create a KubeconfigManager with temporary file."""
    return KubeconfigManager(kubeconfig_path=temp_kubeconfig_path)


class TestKubeconfigManager:
    """Test KubeconfigManager functionality."""

    def test_init_creates_empty_config(self, temp_kubeconfig_path):
        """Test that initialization creates empty kubeconfig structure."""
        # Remove temp file first
        Path(temp_kubeconfig_path).unlink(missing_ok=True)

        KubeconfigManager(kubeconfig_path=temp_kubeconfig_path)

        assert Path(temp_kubeconfig_path).exists()

        with Path(temp_kubeconfig_path).open() as f:
            config = yaml.safe_load(f)

        assert config["apiVersion"] == "v1"
        assert config["kind"] == "Config"
        assert config["clusters"] == []
        assert config["contexts"] == []
        assert config["users"] == []
        assert config["current-context"] == ""

    def test_add_eks_cluster_context(self, kubeconfig_manager, temp_kubeconfig_path):
        """Test adding an EKS cluster context."""
        kubeconfig_manager.add_eks_cluster_context(
            context_name="test-cluster",
            cluster_name="test-eks-cluster",
            endpoint="https://api.test-cluster.eks.amazonaws.com",
            ca_data="base64-encoded-ca-cert",
            token="k8s-aws-v1.token",
            region="us-east-1",
        )

        with Path(temp_kubeconfig_path).open() as f:
            config = yaml.safe_load(f)

        # Verify cluster entry
        assert len(config["clusters"]) == 1
        cluster = config["clusters"][0]
        assert cluster["name"] == "test-cluster"
        assert cluster["cluster"]["server"] == "https://api.test-cluster.eks.amazonaws.com"
        assert cluster["cluster"]["certificate-authority-data"] == "base64-encoded-ca-cert"

        # Verify user entry
        assert len(config["users"]) == 1
        user = config["users"][0]
        assert user["name"] == "test-cluster"
        assert user["user"]["token"] == "k8s-aws-v1.token"

        # Verify context entry
        assert len(config["contexts"]) == 1
        context = config["contexts"][0]
        assert context["name"] == "test-cluster"
        assert context["context"]["cluster"] == "test-cluster"
        assert context["context"]["user"] == "test-cluster"

    def test_add_multiple_contexts(self, kubeconfig_manager, temp_kubeconfig_path):
        """Test adding multiple cluster contexts."""
        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-1",
            cluster_name="eks-cluster-1",
            endpoint="https://api.cluster-1.eks.amazonaws.com",
            ca_data="ca-cert-1",
            token="token-1",
            region="us-east-1",
        )

        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-2",
            cluster_name="eks-cluster-2",
            endpoint="https://api.cluster-2.eks.amazonaws.com",
            ca_data="ca-cert-2",
            token="token-2",
            region="us-west-2",
        )

        with Path(temp_kubeconfig_path).open() as f:
            config = yaml.safe_load(f)

        assert len(config["clusters"]) == 2
        assert len(config["users"]) == 2
        assert len(config["contexts"]) == 2

        # Verify both contexts exist
        context_names = [ctx["name"] for ctx in config["contexts"]]
        assert "cluster-1" in context_names
        assert "cluster-2" in context_names

    def test_update_existing_context(self, kubeconfig_manager, temp_kubeconfig_path):
        """Test updating an existing context with new token."""
        # Add initial context
        kubeconfig_manager.add_eks_cluster_context(
            context_name="test-cluster",
            cluster_name="test-eks-cluster",
            endpoint="https://api.test-cluster.eks.amazonaws.com",
            ca_data="ca-cert-old",
            token="token-old",
            region="us-east-1",
        )

        # Update with new token
        kubeconfig_manager.add_eks_cluster_context(
            context_name="test-cluster",
            cluster_name="test-eks-cluster",
            endpoint="https://api.test-cluster.eks.amazonaws.com",
            ca_data="ca-cert-new",
            token="token-new",
            region="us-east-1",
        )

        with Path(temp_kubeconfig_path).open() as f:
            config = yaml.safe_load(f)

        # Should still have only one context
        assert len(config["clusters"]) == 1
        assert len(config["users"]) == 1
        assert len(config["contexts"]) == 1

        # Verify token was updated
        user = config["users"][0]
        assert user["user"]["token"] == "token-new"

        # Verify CA was updated
        cluster = config["clusters"][0]
        assert cluster["cluster"]["certificate-authority-data"] == "ca-cert-new"

    def test_remove_context(self, kubeconfig_manager, temp_kubeconfig_path):
        """Test removing a context."""
        # Add two contexts
        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-1",
            cluster_name="eks-cluster-1",
            endpoint="https://api.cluster-1.eks.amazonaws.com",
            ca_data="ca-cert-1",
            token="token-1",
            region="us-east-1",
        )

        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-2",
            cluster_name="eks-cluster-2",
            endpoint="https://api.cluster-2.eks.amazonaws.com",
            ca_data="ca-cert-2",
            token="token-2",
            region="us-west-2",
        )

        # Remove one context
        kubeconfig_manager.remove_context("cluster-1")

        with Path(temp_kubeconfig_path).open() as f:
            config = yaml.safe_load(f)

        # Should have only one context remaining
        assert len(config["clusters"]) == 1
        assert len(config["users"]) == 1
        assert len(config["contexts"]) == 1

        # Verify cluster-2 remains
        assert config["contexts"][0]["name"] == "cluster-2"

    def test_get_kubeconfig_path(self, kubeconfig_manager, temp_kubeconfig_path):
        """Test getting kubeconfig path."""
        path = kubeconfig_manager.get_kubeconfig_path()
        assert path == str(Path(temp_kubeconfig_path).absolute())

    def test_list_contexts(self, kubeconfig_manager):
        """Test listing all contexts."""
        # Initially empty
        contexts = kubeconfig_manager.list_contexts()
        assert contexts == []

        # Add contexts
        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-1",
            cluster_name="eks-cluster-1",
            endpoint="https://api.cluster-1.eks.amazonaws.com",
            ca_data="ca-cert-1",
            token="token-1",
            region="us-east-1",
        )

        kubeconfig_manager.add_eks_cluster_context(
            context_name="cluster-2",
            cluster_name="eks-cluster-2",
            endpoint="https://api.cluster-2.eks.amazonaws.com",
            ca_data="ca-cert-2",
            token="token-2",
            region="us-west-2",
        )

        contexts = kubeconfig_manager.list_contexts()
        assert len(contexts) == 2
        assert "cluster-1" in contexts
        assert "cluster-2" in contexts

    def test_default_temp_kubeconfig(self):
        """Test that manager creates temp kubeconfig if no path provided."""
        manager = KubeconfigManager()
        path = manager.get_kubeconfig_path()

        assert Path(path).exists()
        # Verify it's in a temp directory and has guard subdirectory
        assert "guard" in path
        assert path.endswith("kubeconfig")

        # Cleanup
        Path(path).unlink(missing_ok=True)
