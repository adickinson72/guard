"""Unit tests for PodHealthCheck.

This module tests the Kubernetes pod health check that validates
pods are running and ready in specified namespaces.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from guard.checks.kubernetes.pod_health import PodHealthCheck
from guard.core.models import ClusterConfig
from guard.interfaces.check import CheckContext


@pytest.fixture
def pod_health_check() -> PodHealthCheck:
    """Provide a pod health check instance with default namespaces."""
    return PodHealthCheck()


@pytest.fixture
def custom_namespace_check() -> PodHealthCheck:
    """Provide a pod health check with custom namespaces."""
    return PodHealthCheck(namespaces=["istio-system", "kube-system", "monitoring"])


@pytest.fixture
def single_namespace_check() -> PodHealthCheck:
    """Provide a pod health check for a single namespace."""
    return PodHealthCheck(namespaces=["istio-system"])


@pytest.fixture
def mock_k8s_provider() -> MagicMock:
    """Provide a mock Kubernetes provider."""
    provider = MagicMock()
    provider.check_pods_ready = AsyncMock()
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


class TestPodHealthCheckProperties:
    """Tests for PodHealthCheck properties."""

    def test_check_name(self, pod_health_check: PodHealthCheck) -> None:
        """Test that check has correct name."""
        assert pod_health_check.name == "pod_health"

    def test_check_description_default_namespace(self, pod_health_check: PodHealthCheck) -> None:
        """Test that check description includes default namespace."""
        description = pod_health_check.description
        assert "pod" in description.lower()
        assert "kube-system" in description

    def test_check_description_custom_namespaces(
        self, custom_namespace_check: PodHealthCheck
    ) -> None:
        """Test that check description includes custom namespaces."""
        description = custom_namespace_check.description
        assert "istio-system" in description
        assert "kube-system" in description
        assert "monitoring" in description

    def test_check_is_critical_by_default(self, pod_health_check: PodHealthCheck) -> None:
        """Test that pod health check is critical by default."""
        assert pod_health_check.is_critical is True

    def test_check_has_timeout(self, pod_health_check: PodHealthCheck) -> None:
        """Test that check has timeout configured."""
        assert pod_health_check.timeout_seconds > 0
        assert isinstance(pod_health_check.timeout_seconds, int)


class TestPodHealthCheckInitialization:
    """Tests for PodHealthCheck initialization."""

    def test_initialization_default_namespace(self) -> None:
        """Test that check initializes with kube-system by default."""
        check = PodHealthCheck()
        assert check.namespaces == ["kube-system"]

    def test_initialization_custom_namespaces(self) -> None:
        """Test that check initializes with custom namespaces."""
        namespaces = ["istio-system", "monitoring"]
        check = PodHealthCheck(namespaces=namespaces)
        assert check.namespaces == namespaces

    def test_initialization_empty_list_uses_default(self) -> None:
        """Test that empty namespace list falls back to default."""
        check = PodHealthCheck(namespaces=[])
        assert check.namespaces == ["kube-system"]

    def test_initialization_none_uses_default(self) -> None:
        """Test that None namespace list uses default."""
        check = PodHealthCheck(namespaces=None)
        assert check.namespaces == ["kube-system"]


class TestPodHealthCheckSuccess:
    """Tests for successful pod health checks."""

    @pytest.mark.asyncio
    async def test_execute_success_all_pods_ready(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check when all pods are ready."""
        # Mock check_pods_ready to return all ready
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.check_name == "pod_health"
        assert "ready" in result.message.lower()
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_success_multiple_namespaces(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test successful check across multiple namespaces."""
        # All pods ready in all namespaces
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await custom_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        # Should be called once per namespace
        assert mock_context.kubernetes_provider.check_pods_ready.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_success_message_includes_namespaces(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that success message includes namespace information."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await custom_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        # Message should mention the namespaces or indicate success
        assert any(
            ns in result.message
            for ns in ["istio-system", "kube-system", "monitoring"]
        )


class TestPodHealthCheckFailure:
    """Tests for pod health check failures."""

    @pytest.mark.asyncio
    async def test_execute_fails_with_unready_pods(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when some pods are not ready."""
        unready_pods = ["pod-1", "pod-2"]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "pod_health"
        assert "not all pods ready" in result.message.lower()
        assert result.metrics["unready_count"] == 2

    @pytest.mark.asyncio
    async def test_execute_fails_with_unready_pods_multiple_namespaces(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test failure with unready pods across multiple namespaces."""
        # First two namespaces are fine, third has issues
        def check_pods_side_effect(namespace: str):
            if namespace == "monitoring":
                return (False, ["prometheus-pod", "grafana-pod"])
            return (True, [])

        mock_context.kubernetes_provider.check_pods_ready.side_effect = check_pods_side_effect

        result = await custom_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 2
        # Should include namespace prefix
        assert "monitoring/prometheus-pod" in result.metrics["unready_pods"]
        assert "monitoring/grafana-pod" in result.metrics["unready_pods"]

    @pytest.mark.asyncio
    async def test_execute_failure_message_includes_pod_names(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that failure message includes unready pod names."""
        unready_pods = ["istiod-123", "pilot-456"]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        # Message should contain pod names with namespace prefix
        assert "istio-system/" in result.message

    @pytest.mark.asyncio
    async def test_execute_fails_on_api_error(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check fails when API call raises exception."""
        mock_context.kubernetes_provider.check_pods_ready.side_effect = RuntimeError(
            "Failed to check pod status"
        )

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.check_name == "pod_health"
        assert "failed" in result.message.lower()
        assert "Failed to check pod status" in result.message


class TestPodHealthCheckMetrics:
    """Tests for pod health check metrics."""

    @pytest.mark.asyncio
    async def test_execute_includes_unready_count_metric_success(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result includes unready_count metric on success."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert "unready_count" in result.metrics
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_includes_unready_pods_metric_on_failure(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result includes unready_pods list on failure."""
        unready_pods = ["pod-1", "pod-2"]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert "unready_count" in result.metrics
        assert "unready_pods" in result.metrics
        assert result.metrics["unready_count"] == 2
        # Should be prefixed with namespace
        assert result.metrics["unready_pods"] == ["istio-system/pod-1", "istio-system/pod-2"]

    @pytest.mark.asyncio
    async def test_execute_aggregates_unready_pods_from_multiple_namespaces(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that unready pods from multiple namespaces are aggregated."""

        def check_pods_side_effect(namespace: str):
            if namespace == "istio-system":
                return (False, ["istiod-pod"])
            elif namespace == "monitoring":
                return (False, ["prometheus-pod"])
            return (True, [])

        mock_context.kubernetes_provider.check_pods_ready.side_effect = check_pods_side_effect

        result = await custom_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 2
        assert "istio-system/istiod-pod" in result.metrics["unready_pods"]
        assert "monitoring/prometheus-pod" in result.metrics["unready_pods"]

    @pytest.mark.asyncio
    async def test_execute_metrics_empty_on_error(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that metrics are empty when an error occurs."""
        mock_context.kubernetes_provider.check_pods_ready.side_effect = RuntimeError("Error")

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert result.metrics == {}


class TestPodHealthCheckEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_execute_with_many_unready_pods(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test handling of many unready pods."""
        unready_pods = [f"pod-{i}" for i in range(50)]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 50
        # Message should truncate (shows first 5)
        assert "..." in result.message

    @pytest.mark.asyncio
    async def test_execute_message_truncates_long_pod_list(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that message truncates when there are many unready pods."""
        unready_pods = [f"pod-{i}" for i in range(10)]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        # Message should show first 5 pods plus "..."
        assert "..." in result.message
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_execute_with_single_namespace_single_pod(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test check with single namespace and single unready pod."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, ["single-pod"])

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 1
        assert "istio-system/single-pod" in result.metrics["unready_pods"]

    @pytest.mark.asyncio
    async def test_execute_provider_called_per_namespace(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that provider is called once per namespace."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        await custom_namespace_check.execute(sample_cluster_config, mock_context)

        # Should be called for each of the 3 namespaces
        assert mock_context.kubernetes_provider.check_pods_ready.call_count == 3


class TestPodHealthCheckResultStructure:
    """Tests for result structure and content."""

    @pytest.mark.asyncio
    async def test_result_has_required_fields(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result has all required CheckResult fields."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert hasattr(result, "check_name")
        assert hasattr(result, "passed")
        assert hasattr(result, "message")
        assert hasattr(result, "metrics")
        assert hasattr(result, "timestamp")

    @pytest.mark.asyncio
    async def test_result_message_is_descriptive(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result message is descriptive and helpful."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert len(result.message) > 0
        assert isinstance(result.message, str)

    @pytest.mark.asyncio
    async def test_result_check_name_matches(
        self,
        pod_health_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that result check_name matches the check's name property."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await pod_health_check.execute(sample_cluster_config, mock_context)

        assert result.check_name == pod_health_check.name


class TestPodHealthCheckIntegration:
    """Integration tests for realistic scenarios."""

    @pytest.mark.asyncio
    async def test_realistic_all_pods_ready_scenario(
        self,
        custom_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario where all pods are ready."""
        mock_context.kubernetes_provider.check_pods_ready.return_value = (True, [])

        result = await custom_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is True
        assert result.metrics["unready_count"] == 0

    @pytest.mark.asyncio
    async def test_realistic_pod_crash_loop_scenario(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario with pod in crash loop."""
        unready_pods = ["app-pod-crashloop"]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert "istio-system/app-pod-crashloop" in result.metrics["unready_pods"]

    @pytest.mark.asyncio
    async def test_realistic_rolling_update_scenario(
        self,
        single_namespace_check: PodHealthCheck,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test realistic scenario during rolling update."""
        # Some pods being updated might not be ready
        unready_pods = ["app-pod-new-1", "app-pod-new-2"]
        mock_context.kubernetes_provider.check_pods_ready.return_value = (False, unready_pods)

        result = await single_namespace_check.execute(sample_cluster_config, mock_context)

        assert result.passed is False
        assert result.metrics["unready_count"] == 2
