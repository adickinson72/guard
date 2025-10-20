"""Unit tests for NodeReadinessCheck.

This module tests the Kubernetes node readiness check that validates
all cluster nodes are in Ready state before upgrades.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from guard.checks.kubernetes.node_readiness import NodeReadinessCheck
from guard.core.models import ClusterConfig
from guard.interfaces.check import CheckContext


@pytest.fixture
def node_readiness_check() -> NodeReadinessCheck:
    """Provide a node readiness check instance."""
    return NodeReadinessCheck()


@pytest.fixture
def mock_k8s_provider() -> MagicMock:
    """Provide a mock Kubernetes provider."""
    provider = MagicMock()
    provider.check_nodes_ready = AsyncMock()
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


class TestNodeReadinessCheckProperties:
    """Tests for NodeReadinessCheck properties."""

    def test_check_name(self, node_readiness_check: NodeReadinessCheck) -> None:
        """Test that check has correct name."""
        assert node_readiness_check.name == "node_readiness"

    def test_check_description(self, node_readiness_check: NodeReadinessCheck) -> None:
        """Test that check has descriptive text."""
        description = node_readiness_check.description
        assert "node" in description.lower()
        assert "ready" in description.lower()

    def test_check_is_critical_by_default(self, node_readiness_check: NodeReadinessCheck) -> None:
        """Test that node readiness check is critical by default."""
        assert node_readiness_check.is_critical is True

    def test_check_has_timeout(self, node_readiness_check: NodeReadinessCheck) -> None:
        """Test that check has timeout configured."""
        assert node_readiness_check.timeout_seconds > 0
        assert isinstance(node_readiness_check.timeout_seconds, int)


class TestNodeReadinessCheckSuccess:
    """Tests for successful node readiness checks."""

    @pytest.mark.asyncio
    async def test_execute_success_all_nodes_ready(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check when all nodes are ready."""
        # Mock check_nodes_ready to return all ready
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.check_name == "node_readiness"
        assert "ready" in result.message.lower()
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_success_message_indicates_all_ready(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that success message clearly indicates all nodes are ready."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert "all" in result.message.lower()
        assert "ready" in result.message.lower()


class TestNodeReadinessCheckFailure:
    """Tests for node readiness check failures."""

    @pytest.mark.asyncio
    async def test_execute_fails_with_unready_nodes(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when some nodes are not ready."""
        unready_nodes = ["node-1", "node-2"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "node_readiness"
        assert "not all nodes ready" in result.message.lower()
        assert result.metrics["unready_count"] == 2
        assert result.metrics["unready_nodes"] == unready_nodes

    @pytest.mark.asyncio
    async def test_execute_fails_with_single_unready_node(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when a single node is not ready."""
        unready_nodes = ["node-1"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 1
        assert "node-1" in result.message

    @pytest.mark.asyncio
    async def test_execute_failure_message_includes_node_names(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that failure message includes unready node names."""
        unready_nodes = ["node-alpha", "node-beta", "node-gamma"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        # Message should contain at least some node names
        assert any(node in result.message for node in unready_nodes)

    @pytest.mark.asyncio
    async def test_execute_fails_on_api_error(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when API call raises exception."""
        mock_context.kubernetes_provider.check_nodes_ready.side_effect = RuntimeError(
            "Failed to check node status"
        )

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "node_readiness"
        assert "failed" in result.message.lower()
        assert "Failed to check node status" in result.message

    @pytest.mark.asyncio
    async def test_execute_fails_on_connection_error(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails on connection errors."""
        mock_context.kubernetes_provider.check_nodes_ready.side_effect = ConnectionError(
            "Connection refused"
        )

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert "Connection refused" in result.message


class TestNodeReadinessCheckMetrics:
    """Tests for node readiness check metrics."""

    @pytest.mark.asyncio
    async def test_execute_includes_unready_count_metric_success(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result includes unready_count metric on success."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert "unready_count" in result.metrics
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_includes_unready_nodes_metric_on_failure(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result includes unready_nodes list on failure."""
        unready_nodes = ["node-1", "node-2"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert "unready_count" in result.metrics
        assert "unready_nodes" in result.metrics
        assert result.metrics["unready_count"] == 2
        assert result.metrics["unready_nodes"] == unready_nodes

    @pytest.mark.asyncio
    async def test_execute_metrics_empty_on_error(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that metrics are empty when an error occurs."""
        mock_context.kubernetes_provider.check_nodes_ready.side_effect = RuntimeError("Error")

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.metrics == {}


class TestNodeReadinessCheckEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_execute_with_many_unready_nodes(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test handling of many unready nodes."""
        unready_nodes = [f"node-{i}" for i in range(20)]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 20
        assert len(result.metrics["unready_nodes"]) == 20

    @pytest.mark.asyncio
    async def test_execute_with_empty_unready_list_but_not_ready(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test handling of inconsistent state (not ready but no unready nodes)."""
        # Edge case: provider says not ready but returns empty list
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        # Should still fail since all_ready is False
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_execute_with_different_cluster_configs(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        sample_prod_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check works with different cluster configurations."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        # Test with test cluster
        result1 = await node_readiness_check.execute(sample_cluster_config, mock_context)
        assert result1.passed is True

        # Test with prod cluster
        result2 = await node_readiness_check.execute(sample_prod_cluster_config, mock_context)
        assert result2.passed is True

    @pytest.mark.asyncio
    async def test_execute_provider_called_once(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that Kubernetes provider is called exactly once."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        await node_readiness_check.execute(sample_cluster_config, mock_context)

        mock_context.kubernetes_provider.check_nodes_ready.assert_called_once()


class TestNodeReadinessCheckResultStructure:
    """Tests for result structure and content."""

    @pytest.mark.asyncio
    async def test_result_has_required_fields(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result has all required CheckResult fields."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert hasattr(result, "check_name")
        assert hasattr(result, "passed")
        assert hasattr(result, "message")
        assert hasattr(result, "metrics")
        assert hasattr(result, "timestamp")

    @pytest.mark.asyncio
    async def test_result_message_is_descriptive(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result message is descriptive and helpful."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert len(result.message) > 0
        assert isinstance(result.message, str)

    @pytest.mark.asyncio
    async def test_result_check_name_matches(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result check_name matches the check's name property."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.check_name == node_readiness_check.name


class TestNodeReadinessCheckIntegration:
    """Integration tests for realistic scenarios."""

    @pytest.mark.asyncio
    async def test_realistic_all_nodes_ready_scenario(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario where all nodes are ready."""
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (True, [])

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_realistic_node_maintenance_scenario(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario where a node is in maintenance."""
        unready_nodes = ["node-under-maintenance"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert "node-under-maintenance" in result.message
        assert result.metrics["unready_count"] == 1

    @pytest.mark.asyncio
    async def test_realistic_cluster_scaling_scenario(
        self,
        node_readiness_check: NodeReadinessCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario where new nodes are joining."""
        # New nodes joining might not be ready yet
        unready_nodes = ["node-new-1", "node-new-2"]
        mock_context.kubernetes_provider.check_nodes_ready.return_value = (False, unready_nodes)

        result = await node_readiness_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 2
