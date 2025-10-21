"""Unit tests for ControlPlaneHealthCheck.

This module tests the Kubernetes control plane health check that
validates the control plane is accessible and responsive.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from guard.checks.kubernetes.control_plane import ControlPlaneHealthCheck
from guard.core.models import ClusterConfig
from guard.interfaces.check import CheckContext
from guard.interfaces.kubernetes_provider import NodeInfo


@pytest.fixture
def control_plane_check() -> ControlPlaneHealthCheck:
    """Provide a control plane health check instance."""
    return ControlPlaneHealthCheck()


@pytest.fixture
def mock_k8s_provider() -> MagicMock:
    """Provide a mock Kubernetes provider."""
    provider = MagicMock()
    provider.get_nodes = AsyncMock()
    return provider


@pytest.fixture
def mock_context(mock_k8s_provider: MagicMock) -> CheckContext:
    """Provide a mock check context with Kubernetes provider."""
    return CheckContext(
        cloud_provider=MagicMock(),
        kubernetes_provider=mock_k8s_provider,
        metrics_provider=MagicMock(),
        extra_context={},
    )


class TestControlPlaneCheckProperties:
    """Tests for ControlPlaneHealthCheck properties."""

    def test_check_name(self, control_plane_check: ControlPlaneHealthCheck) -> None:
        """Test that check has correct name."""
        assert control_plane_check.name == "control_plane_health"

    def test_check_description(self, control_plane_check: ControlPlaneHealthCheck) -> None:
        """Test that check has descriptive text."""
        description = control_plane_check.description
        assert "control plane" in description.lower()
        assert "kubernetes" in description.lower()

    def test_check_is_critical_by_default(
        self, control_plane_check: ControlPlaneHealthCheck
    ) -> None:
        """Test that control plane check is critical by default."""
        assert control_plane_check.is_critical is True

    def test_check_has_timeout(self, control_plane_check: ControlPlaneHealthCheck) -> None:
        """Test that check has timeout configured."""
        assert control_plane_check.timeout_seconds > 0
        assert isinstance(control_plane_check.timeout_seconds, int)


class TestControlPlaneCheckSuccess:
    """Tests for successful control plane checks."""

    @pytest.mark.asyncio
    async def test_execute_success_with_nodes(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check when nodes are found."""
        # Mock get_nodes to return sample nodes
        mock_nodes = [
            NodeInfo(
                name="node-1",
                ready=True,
                conditions={"Ready": "True"},
                capacity={"cpu": "4", "memory": "8Gi"},
                allocatable={"cpu": "4", "memory": "8Gi"},
            ),
            NodeInfo(
                name="node-2",
                ready=True,
                conditions={"Ready": "True"},
                capacity={"cpu": "4", "memory": "8Gi"},
                allocatable={"cpu": "4", "memory": "8Gi"},
            ),
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.check_name == "control_plane_health"
        assert "healthy" in result.message.lower()
        assert "2" in result.message or "nodes" in result.message.lower()
        assert result.metrics["node_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_success_single_node(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check with single node cluster."""
        mock_nodes = [
            NodeInfo(
                name="node-1",
                ready=True,
                conditions={"Ready": "True"},
                capacity={"cpu": "2", "memory": "4Gi"},
                allocatable={"cpu": "2", "memory": "4Gi"},
            )
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.metrics["node_count"] == 1

    @pytest.mark.asyncio
    async def test_execute_success_many_nodes(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check with many nodes."""
        # Create 10 mock nodes
        mock_nodes = [
            NodeInfo(
                name=f"node-{i}",
                ready=True,
                conditions={"Ready": "True"},
                capacity={"cpu": "4", "memory": "8Gi"},
                allocatable={"cpu": "4", "memory": "8Gi"},
            )
            for i in range(10)
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.metrics["node_count"] == 10


class TestControlPlaneCheckFailure:
    """Tests for control plane check failures."""

    @pytest.mark.asyncio
    async def test_execute_fails_when_no_nodes(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when no nodes are found."""
        mock_context.kubernetes_provider.get_nodes.return_value = []

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "control_plane_health"
        assert "no nodes" in result.message.lower()
        assert result.metrics["node_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_fails_on_api_error(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when API call raises exception."""
        mock_context.kubernetes_provider.get_nodes.side_effect = RuntimeError(
            "API server unreachable"
        )

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "control_plane_health"
        assert "unhealthy" in result.message.lower()
        assert "API server unreachable" in result.message

    @pytest.mark.asyncio
    async def test_execute_fails_on_connection_error(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails on connection errors."""
        mock_context.kubernetes_provider.get_nodes.side_effect = ConnectionError(
            "Connection refused"
        )

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_execute_fails_on_timeout(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails on timeout."""
        mock_context.kubernetes_provider.get_nodes.side_effect = TimeoutError("Request timed out")

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert "timed out" in result.message.lower()


class TestControlPlaneCheckMetrics:
    """Tests for control plane check metrics."""

    @pytest.mark.asyncio
    async def test_execute_includes_node_count_metric(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result includes node_count metric."""
        mock_nodes = [
            NodeInfo(
                name="node-1",
                ready=True,
                conditions={},
                capacity={},
                allocatable={},
            )
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert "node_count" in result.metrics
        assert isinstance(result.metrics["node_count"], int)

    @pytest.mark.asyncio
    async def test_execute_metrics_empty_on_error(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that metrics are empty when an error occurs."""
        mock_context.kubernetes_provider.get_nodes.side_effect = RuntimeError("Error")

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert result.metrics == {}


class TestControlPlaneCheckEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_execute_handles_none_response(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check handles None response from provider."""
        mock_context.kubernetes_provider.get_nodes.return_value = None

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        # None is falsy, should be treated as no nodes
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_execute_with_different_cluster_configs(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        sample_prod_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check works with different cluster configurations."""
        mock_nodes = [
            NodeInfo(
                name="node-1",
                ready=True,
                conditions={},
                capacity={},
                allocatable={},
            )
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        # Test with test cluster
        result1 = await control_plane_check.execute(sample_cluster_config, mock_context)
        assert result1.passed is True

        # Test with prod cluster
        result2 = await control_plane_check.execute(sample_prod_cluster_config, mock_context)
        assert result2.passed is True

    @pytest.mark.asyncio
    async def test_execute_provider_called_once(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that Kubernetes provider is called exactly once."""
        mock_context.kubernetes_provider.get_nodes.return_value = []

        await control_plane_check.execute(sample_cluster_config, mock_context)

        mock_context.kubernetes_provider.get_nodes.assert_called_once()


class TestControlPlaneCheckResultStructure:
    """Tests for result structure and content."""

    @pytest.mark.asyncio
    async def test_result_has_required_fields(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result has all required CheckResult fields."""
        mock_context.kubernetes_provider.get_nodes.return_value = []

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert hasattr(result, "check_name")
        assert hasattr(result, "passed")
        assert hasattr(result, "message")
        assert hasattr(result, "metrics")
        assert hasattr(result, "timestamp")

    @pytest.mark.asyncio
    async def test_result_message_is_descriptive(
        self,
        control_plane_check: ControlPlaneHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result message is descriptive and helpful."""
        mock_nodes = [
            NodeInfo(name="node-1", ready=True, conditions={}, capacity={}, allocatable={})
        ]
        mock_context.kubernetes_provider.get_nodes.return_value = mock_nodes

        result = await control_plane_check.execute(sample_cluster_config, mock_context)

        assert len(result.message) > 0
        assert isinstance(result.message, str)
        # Should mention health status and node count
        assert any(word in result.message.lower() for word in ["healthy", "found", "node"])
