"""Unit tests for IstioCtlAnalyzeCheck.

This module tests the IstioCtlAnalyzeCheck which validates Istio configuration
using istioctl analyze to detect potential issues before upgrades.
"""

from unittest.mock import MagicMock, patch

import pytest

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import CheckContext
from guard.services.istio.checks.istioctl_analyze import IstioCtlAnalyzeCheck


@pytest.fixture
def istioctl_check() -> IstioCtlAnalyzeCheck:
    """Create IstioCtlAnalyzeCheck instance for testing.

    Returns:
        IstioCtlAnalyzeCheck instance
    """
    return IstioCtlAnalyzeCheck()


@pytest.fixture
def mock_istioctl_wrapper() -> MagicMock:
    """Create mock IstioctlWrapper for testing.

    Returns:
        Mock IstioctlWrapper
    """
    wrapper = MagicMock()
    wrapper.analyze.return_value = (True, "No validation issues found")
    return wrapper


@pytest.fixture
def sample_check_context(mock_istioctl_wrapper: MagicMock) -> CheckContext:
    """Create sample CheckContext with mocked dependencies.

    Args:
        mock_istioctl_wrapper: Mock IstioctlWrapper

    Returns:
        CheckContext instance
    """
    return CheckContext(
        cloud_provider=MagicMock(),
        kubernetes_provider=MagicMock(),
        metrics_provider=MagicMock(),
        extra_context={"istioctl": mock_istioctl_wrapper},
    )


class TestIstioCtlAnalyzeCheckProperties:
    """Test IstioCtlAnalyzeCheck properties."""

    def test_check_name(self, istioctl_check: IstioCtlAnalyzeCheck):
        """Test that check has correct name.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
        """
        assert istioctl_check.name == "istioctl_analyze"

    def test_check_description(self, istioctl_check: IstioCtlAnalyzeCheck):
        """Test that check has proper description.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
        """
        assert istioctl_check.description == "Validates Istio configuration using istioctl analyze"
        assert "istioctl" in istioctl_check.description.lower()
        assert "analyze" in istioctl_check.description.lower()

    def test_timeout_seconds(self, istioctl_check: IstioCtlAnalyzeCheck):
        """Test that check has appropriate timeout.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
        """
        assert istioctl_check.timeout_seconds == 120
        assert istioctl_check.timeout_seconds > 0

    def test_is_critical_default(self, istioctl_check: IstioCtlAnalyzeCheck):
        """Test that check is critical by default.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
        """
        assert istioctl_check.is_critical is True


class TestIstioCtlAnalyzeCheckExecution:
    """Test IstioCtlAnalyzeCheck execution."""

    @pytest.mark.asyncio
    async def test_execute_with_no_issues(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution when istioctl analyze finds no issues.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        # Mock istioctl to return no issues
        mock_istioctl_wrapper.analyze.return_value = (True, "No validation issues found")

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert isinstance(result, CheckResult)
        assert result.check_name == "istioctl_analyze"
        assert result.passed is True
        assert "no errors" in result.message.lower()
        assert result.metrics["issues_found"] == 0

        # Verify istioctl was called correctly
        mock_istioctl_wrapper.analyze.assert_called_once_with(namespace=None)

    @pytest.mark.asyncio
    async def test_execute_with_errors_and_warnings(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution when istioctl analyze finds errors and warnings.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        # Mock istioctl to return issues
        output = """Error [IST0101] (Deployment foo/bar) Referenced service not found
Warning [IST0118] (Pod foo/baz) Port 443 is exposed
Error [IST0102] (VirtualService foo/qux) Host not found"""

        mock_istioctl_wrapper.analyze.return_value = (False, output)

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert isinstance(result, CheckResult)
        assert result.check_name == "istioctl_analyze"
        assert result.passed is False
        assert "2 errors" in result.message
        assert "1 warnings" in result.message
        assert result.metrics["issues_found"] == 3
        assert result.metrics["errors"] == 2
        assert result.metrics["warnings"] == 1

    @pytest.mark.asyncio
    async def test_execute_with_only_warnings(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution when istioctl analyze finds only warnings.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        output = """Warning [IST0118] (Pod foo/bar) Port 443 is exposed
Warning [IST0119] (Service foo/baz) Service port name does not follow convention"""

        mock_istioctl_wrapper.analyze.return_value = (False, output)

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is False
        assert result.metrics["errors"] == 0
        assert result.metrics["warnings"] == 2
        assert result.metrics["issues_found"] == 2

    @pytest.mark.asyncio
    async def test_execute_with_only_errors(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution when istioctl analyze finds only errors.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        output = """Error [IST0101] (Deployment foo/bar) Referenced service not found
Error [IST0102] (VirtualService foo/baz) Host not found
Error [IST0103] (DestinationRule foo/qux) Invalid subset"""

        mock_istioctl_wrapper.analyze.return_value = (False, output)

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is False
        assert result.metrics["errors"] == 3
        assert result.metrics["warnings"] == 0
        assert result.metrics["issues_found"] == 3


class TestIstioCtlAnalyzeCheckWithoutContext:
    """Test IstioCtlAnalyzeCheck when istioctl is not in context."""

    @pytest.mark.asyncio
    async def test_execute_creates_istioctl_wrapper_when_not_in_context(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
    ):
        """Test that check creates IstioctlWrapper when not provided in context.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
        """
        # Context without istioctl
        context = CheckContext(
            cloud_provider=MagicMock(),
            kubernetes_provider=MagicMock(),
            metrics_provider=MagicMock(),
            extra_context={"kubeconfig_path": "/path/to/kubeconfig"},
        )

        with patch("guard.clients.istioctl.IstioctlWrapper") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = (True, "No issues")
            mock_class.return_value = mock_instance

            result = await istioctl_check.execute(sample_cluster_config, context)

            # Verify IstioctlWrapper was created
            mock_class.assert_called_once_with(
                kubeconfig_path="/path/to/kubeconfig",
                context=sample_cluster_config.cluster_id,
            )

            assert result.passed is True

    @pytest.mark.asyncio
    async def test_execute_creates_istioctl_wrapper_without_kubeconfig(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
    ):
        """Test that check creates IstioctlWrapper without kubeconfig path.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
        """
        # Context without istioctl or kubeconfig
        context = CheckContext(
            cloud_provider=MagicMock(),
            kubernetes_provider=MagicMock(),
            metrics_provider=MagicMock(),
            extra_context={},
        )

        with patch("guard.clients.istioctl.IstioctlWrapper") as mock_class:
            mock_instance = MagicMock()
            mock_instance.analyze.return_value = (True, "No issues")
            mock_class.return_value = mock_instance

            result = await istioctl_check.execute(sample_cluster_config, context)

            # Verify IstioctlWrapper was created with None kubeconfig
            mock_class.assert_called_once_with(
                kubeconfig_path=None,
                context=sample_cluster_config.cluster_id,
            )

            assert result.passed is True


class TestIstioCtlAnalyzeCheckErrorHandling:
    """Test IstioCtlAnalyzeCheck error handling."""

    @pytest.mark.asyncio
    async def test_execute_handles_istioctl_exception(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test that execution handles istioctl exceptions gracefully.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        # Mock istioctl to raise exception
        mock_istioctl_wrapper.analyze.side_effect = Exception("istioctl not found")

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert isinstance(result, CheckResult)
        assert result.check_name == "istioctl_analyze"
        assert result.passed is False
        assert "failed" in result.message.lower()
        assert "istioctl not found" in result.message
        assert result.metrics == {}

    @pytest.mark.asyncio
    async def test_execute_handles_network_error(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test that execution handles network errors gracefully.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        mock_istioctl_wrapper.analyze.side_effect = ConnectionError("Connection refused")

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is False
        assert "failed" in result.message.lower()
        assert result.metrics == {}

    @pytest.mark.asyncio
    async def test_execute_logs_errors(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test that execution logs errors appropriately.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        mock_istioctl_wrapper.analyze.side_effect = Exception("Test error")

        with patch("guard.services.istio.checks.istioctl_analyze.logger") as mock_logger:
            result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args[0][0] == "istioctl_analyze_failed"
            assert call_args[1]["cluster_id"] == sample_cluster_config.cluster_id
            assert "Test error" in call_args[1]["error"]

            assert result.passed is False


class TestIstioCtlAnalyzeCheckLogging:
    """Test IstioCtlAnalyzeCheck logging."""

    @pytest.mark.asyncio
    async def test_execute_logs_success(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
    ):
        """Test that successful execution is logged.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
        """
        with patch("guard.services.istio.checks.istioctl_analyze.logger") as mock_logger:
            await istioctl_check.execute(sample_cluster_config, sample_check_context)

            # Verify info log was called
            mock_logger.info.assert_called_once_with(
                "running_istioctl_analyze", cluster_id=sample_cluster_config.cluster_id
            )

    @pytest.mark.asyncio
    async def test_execute_logs_cluster_id(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
    ):
        """Test that cluster_id is included in logs.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
        """
        with patch("guard.services.istio.checks.istioctl_analyze.logger") as mock_logger:
            await istioctl_check.execute(sample_cluster_config, sample_check_context)

            # All log calls should include cluster_id
            for call in mock_logger.info.call_args_list:
                if len(call[1]) > 0:
                    assert "cluster_id" in call[1]


class TestIstioCtlAnalyzeCheckEdgeCases:
    """Test IstioCtlAnalyzeCheck edge cases."""

    @pytest.mark.asyncio
    async def test_execute_with_empty_output(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution with empty output from istioctl.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        mock_istioctl_wrapper.analyze.return_value = (True, "")

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is True
        assert result.metrics["issues_found"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_multiline_output(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution with multiline output including non-issue lines.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        output = """Analyzing namespace: default
Error [IST0101] (Deployment foo/bar) Referenced service not found
Analyzing namespace: istio-system
Warning [IST0118] (Pod foo/baz) Port 443 is exposed
Analysis complete"""

        mock_istioctl_wrapper.analyze.return_value = (False, output)

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        # Should only count lines with Error or Warning
        assert result.metrics["errors"] == 1
        assert result.metrics["warnings"] == 1
        assert result.metrics["issues_found"] == 2

    @pytest.mark.asyncio
    async def test_execute_with_mixed_case_issue_types(
        self,
        istioctl_check: IstioCtlAnalyzeCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_istioctl_wrapper: MagicMock,
    ):
        """Test execution with mixed case Error/Warning in output.

        Args:
            istioctl_check: IstioCtlAnalyzeCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_istioctl_wrapper: Mock IstioctlWrapper
        """
        output = """Error [IST0101] (Deployment foo/bar) Referenced service not found
Warning [IST0118] (Pod foo/baz) Port 443 is exposed"""

        mock_istioctl_wrapper.analyze.return_value = (False, output)

        result = await istioctl_check.execute(sample_cluster_config, sample_check_context)

        # Should count both (case-sensitive matching via "in" operator checks for "Error" and "Warning")
        assert result.metrics["issues_found"] == 2
        assert result.metrics["errors"] == 1
        assert result.metrics["warnings"] == 1
