"""Contract tests for Check interface.

All Check implementations must pass these tests to ensure substitutability.
"""

import pytest

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext


class CheckContract:
    """Base contract tests for Check interface."""

    @pytest.fixture
    def check(self) -> Check:
        """Subclass must provide concrete Check implementation."""
        raise NotImplementedError("Subclass must implement check fixture")

    @pytest.fixture
    def sample_cluster(self) -> ClusterConfig:
        """Sample cluster configuration for testing."""
        from guard.core.models import DatadogTags

        return ClusterConfig(
            cluster_id="test-cluster-1",
            batch_id="test",
            environment="test",
            region="us-east-1",
            gitlab_repo="test/repo",
            flux_config_path="test/path.yaml",
            aws_role_arn="arn:aws:iam::123:role/test",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="test-cluster-1", env="test"),
            owner_team="test-team",
            owner_handle="test-user",
        )

    @pytest.fixture
    def mock_context(self) -> CheckContext:
        """Mock check context."""
        return CheckContext(
            cloud_provider=None,
            kubernetes_provider=None,
            metrics_provider=None,
            extra_context={},
        )

    def test_check_has_name(self, check: Check):
        """Check must have a name."""
        assert hasattr(check, "name")
        assert isinstance(check.name, str)
        assert len(check.name) > 0

    def test_check_has_description(self, check: Check):
        """Check must have a description."""
        assert hasattr(check, "description")
        assert isinstance(check.description, str)
        assert len(check.description) > 0

    def test_check_has_is_critical(self, check: Check):
        """Check must have is_critical property."""
        assert hasattr(check, "is_critical")
        assert isinstance(check.is_critical, bool)

    def test_check_has_timeout_seconds(self, check: Check):
        """Check must have timeout_seconds property."""
        assert hasattr(check, "timeout_seconds")
        assert isinstance(check.timeout_seconds, int)
        assert check.timeout_seconds > 0

    @pytest.mark.asyncio
    async def test_execute_returns_check_result(
        self,
        check: Check,
        sample_cluster: ClusterConfig,
        mock_context: CheckContext,
    ):
        """Execute must return CheckResult."""
        result = await check.execute(sample_cluster, mock_context)

        assert isinstance(result, CheckResult)
        assert hasattr(result, "check_name")
        assert hasattr(result, "passed")
        assert hasattr(result, "message")
        assert isinstance(result.passed, bool)
        assert isinstance(result.message, str)


# Example usage:
# class TestControlPlaneHealthCheck(CheckContract):
#     @pytest.fixture
#     def check(self):
#         from guard.checks.kubernetes.control_plane import ControlPlaneHealthCheck
#         return ControlPlaneHealthCheck()
