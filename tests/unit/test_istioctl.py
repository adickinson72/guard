"""Unit tests for istioctl wrapper.

This module tests the IstioctlWrapper for Istio CLI operations including:
- Command execution
- Configuration analysis
- Proxy status checks
- Version retrieval
- Installation verification
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from guard.clients.istioctl import IstioctlWrapper
from guard.core.exceptions import IstioError


class TestIstioctlWrapperInitialization:
    """Tests for IstioctlWrapper initialization."""

    def test_istioctl_wrapper_initialization_default(self) -> None:
        """Test IstioctlWrapper initializes with default settings."""
        wrapper = IstioctlWrapper()

        assert wrapper.kubeconfig_path is None
        assert wrapper.context is None

    def test_istioctl_wrapper_initialization_with_kubeconfig(self) -> None:
        """Test IstioctlWrapper initializes with kubeconfig path."""
        wrapper = IstioctlWrapper(kubeconfig_path="/path/to/kubeconfig")

        assert wrapper.kubeconfig_path == "/path/to/kubeconfig"

    def test_istioctl_wrapper_initialization_with_context(self) -> None:
        """Test IstioctlWrapper initializes with context."""
        wrapper = IstioctlWrapper(context="test-context")

        assert wrapper.context == "test-context"

    def test_istioctl_wrapper_initialization_with_both(self) -> None:
        """Test IstioctlWrapper initializes with both kubeconfig and context."""
        wrapper = IstioctlWrapper(
            kubeconfig_path="/path/to/kubeconfig", context="test-context"
        )

        assert wrapper.kubeconfig_path == "/path/to/kubeconfig"
        assert wrapper.context == "test-context"


class TestRunCommand:
    """Tests for _run_command method."""

    def test_run_command_success(self) -> None:
        """Test successful command execution."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Success output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper._run_command(["version"])

            assert result.returncode == 0
            assert result.stdout == "Success output"

            # Verify subprocess.run was called correctly
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0][0] == "istioctl"
            assert "version" in call_args[0][0]

    def test_run_command_with_kubeconfig(self) -> None:
        """Test command execution includes kubeconfig flag."""
        wrapper = IstioctlWrapper(kubeconfig_path="/path/to/kubeconfig")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper._run_command(["analyze"])

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "--kubeconfig" in cmd
            assert "/path/to/kubeconfig" in cmd

    def test_run_command_with_context(self) -> None:
        """Test command execution includes context flag."""
        wrapper = IstioctlWrapper(context="test-context")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper._run_command(["analyze"])

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "--context" in cmd
            assert "test-context" in cmd

    def test_run_command_failure(self) -> None:
        """Test command execution raises IstioError on failure."""
        wrapper = IstioctlWrapper()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["istioctl"], stderr="Command failed"
            )

            with pytest.raises(IstioError) as exc_info:
                wrapper._run_command(["invalid-command"])

            assert "istioctl command failed" in str(exc_info.value)

    def test_run_command_istioctl_not_found(self) -> None:
        """Test command execution raises IstioError when istioctl not found."""
        wrapper = IstioctlWrapper()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("istioctl not found")

            with pytest.raises(IstioError) as exc_info:
                wrapper._run_command(["version"])

            assert "istioctl command not found" in str(exc_info.value)

    def test_run_command_check_false(self) -> None:
        """Test command execution with check=False doesn't raise on non-zero exit."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "warning output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper._run_command(["analyze"], check=False)

            assert result.returncode == 1
            assert result.stdout == "warning output"


class TestAnalyze:
    """Tests for analyze method."""

    def test_analyze_success_no_issues(self) -> None:
        """Test analyze returns success when no issues found."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "✔ No validation issues found"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            no_issues, output = wrapper.analyze()

            assert no_issues is True
            assert "No validation issues found" in output

    def test_analyze_success_with_issues(self) -> None:
        """Test analyze returns issues when configuration problems found."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "Error [IST0101] (VirtualService.default): Missing gateway"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            no_issues, output = wrapper.analyze()

            assert no_issues is False
            assert "IST0101" in output

    def test_analyze_with_namespace(self) -> None:
        """Test analyze includes namespace flag when specified."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "✔ No issues in istio-system"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result) as mock_cmd:
            wrapper.analyze(namespace="istio-system")

            # Verify namespace flag was included
            call_args = mock_cmd.call_args
            assert "-n" in call_args[0][0]
            assert "istio-system" in call_args[0][0]

    def test_analyze_exception(self) -> None:
        """Test analyze raises IstioError on exception."""
        wrapper = IstioctlWrapper()

        with patch.object(wrapper, "_run_command") as mock_cmd:
            mock_cmd.side_effect = Exception("Unexpected error")

            with pytest.raises(IstioError) as exc_info:
                wrapper.analyze()

            assert "Failed to run istioctl analyze" in str(exc_info.value)


class TestProxyStatus:
    """Tests for proxy_status method."""

    def test_proxy_status_success(self) -> None:
        """Test successful proxy status retrieval."""
        wrapper = IstioctlWrapper()

        proxy_status_data = {
            "syncStatus": [
                {
                    "proxy": "istio-ingressgateway-123.istio-system",
                    "syncStatus": "SYNCED",
                },
                {"proxy": "pod-456.default", "syncStatus": "SYNCED"},
            ]
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(proxy_status_data)
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            result = wrapper.proxy_status()

            assert "syncStatus" in result
            assert len(result["syncStatus"]) == 2

    def test_proxy_status_json_parse_error(self) -> None:
        """Test proxy_status raises IstioError on invalid JSON."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            with pytest.raises(IstioError) as exc_info:
                wrapper.proxy_status()

            assert "Failed to parse proxy status JSON" in str(exc_info.value)

    def test_proxy_status_command_failure(self) -> None:
        """Test proxy_status raises IstioError on command failure."""
        wrapper = IstioctlWrapper()

        with patch.object(wrapper, "_run_command") as mock_cmd:
            mock_cmd.side_effect = IstioError("Command failed")

            with pytest.raises(IstioError) as exc_info:
                wrapper.proxy_status()

            assert "Failed to get proxy status" in str(exc_info.value)


class TestVersion:
    """Tests for version method."""

    def test_version_success(self) -> None:
        """Test successful version retrieval."""
        wrapper = IstioctlWrapper()

        version_data = {
            "clientVersion": {"version": "1.20.0"},
            "meshVersion": [{"Component": "istiod", "Info": {"version": "1.20.0"}}],
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(version_data)
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            result = wrapper.version()

            assert result["clientVersion"]["version"] == "1.20.0"
            assert len(result["meshVersion"]) == 1

    def test_version_json_parse_error(self) -> None:
        """Test version raises IstioError on invalid JSON."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            with pytest.raises(IstioError) as exc_info:
                wrapper.version()

            assert "Failed to parse version JSON" in str(exc_info.value)

    def test_version_command_failure(self) -> None:
        """Test version raises IstioError on command failure."""
        wrapper = IstioctlWrapper()

        with patch.object(wrapper, "_run_command") as mock_cmd:
            mock_cmd.side_effect = IstioError("Command failed")

            with pytest.raises(IstioError) as exc_info:
                wrapper.version()

            assert "Failed to get Istio version" in str(exc_info.value)


class TestCheckProxySync:
    """Tests for check_proxy_sync method."""

    def test_check_proxy_sync_all_synced_list_format(self) -> None:
        """Test check_proxy_sync returns all synced with list format."""
        wrapper = IstioctlWrapper()

        proxy_status = [
            {"name": "proxy-1", "sync_status": "SYNCED"},
            {"name": "proxy-2", "sync_status": "SYNCED"},
            {"name": "proxy-3", "sync_status": "SYNCED"},
        ]

        with patch.object(wrapper, "proxy_status", return_value=proxy_status):
            all_synced, unsynced = wrapper.check_proxy_sync()

            assert all_synced is True
            assert unsynced == []

    def test_check_proxy_sync_some_unsynced_list_format(self) -> None:
        """Test check_proxy_sync detects unsynced proxies in list format."""
        wrapper = IstioctlWrapper()

        proxy_status = [
            {"name": "proxy-1", "sync_status": "SYNCED"},
            {"name": "proxy-2", "sync_status": "NOT_SENT"},
            {"name": "proxy-3", "sync_status": "SYNCED"},
            {"name": "proxy-4", "sync_status": "STALE"},
        ]

        with patch.object(wrapper, "proxy_status", return_value=proxy_status):
            all_synced, unsynced = wrapper.check_proxy_sync()

            assert all_synced is False
            assert len(unsynced) == 2
            assert "proxy-2" in unsynced
            assert "proxy-4" in unsynced

    def test_check_proxy_sync_all_synced_dict_format(self) -> None:
        """Test check_proxy_sync returns all synced with dict format."""
        wrapper = IstioctlWrapper()

        proxy_status = {
            "proxy-1": {"sync_status": "SYNCED"},
            "proxy-2": {"sync_status": "SYNCED"},
        }

        with patch.object(wrapper, "proxy_status", return_value=proxy_status):
            all_synced, unsynced = wrapper.check_proxy_sync()

            assert all_synced is True
            assert unsynced == []

    def test_check_proxy_sync_some_unsynced_dict_format(self) -> None:
        """Test check_proxy_sync detects unsynced proxies in dict format."""
        wrapper = IstioctlWrapper()

        proxy_status = {
            "proxy-1": {"sync_status": "SYNCED"},
            "proxy-2": {"sync_status": "NOT_SENT"},
            "proxy-3": {"sync_status": "SYNCED"},
        }

        with patch.object(wrapper, "proxy_status", return_value=proxy_status):
            all_synced, unsynced = wrapper.check_proxy_sync()

            assert all_synced is False
            assert len(unsynced) == 1
            assert "proxy-2" in unsynced

    def test_check_proxy_sync_exception(self) -> None:
        """Test check_proxy_sync raises IstioError on exception."""
        wrapper = IstioctlWrapper()

        with patch.object(wrapper, "proxy_status") as mock_status:
            mock_status.side_effect = Exception("Unexpected error")

            with pytest.raises(IstioError) as exc_info:
                wrapper.check_proxy_sync()

            assert "Failed to check proxy sync" in str(exc_info.value)


class TestVerifyInstall:
    """Tests for verify_install method."""

    def test_verify_install_success(self) -> None:
        """Test successful installation verification."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "✔ Istio is installed and verified"
        mock_result.stderr = ""

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            verified, output = wrapper.verify_install()

            assert verified is True
            assert "installed and verified" in output

    def test_verify_install_failure(self) -> None:
        """Test installation verification detects issues."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "✗ Missing Istio components"

        with patch.object(wrapper, "_run_command", return_value=mock_result):
            verified, output = wrapper.verify_install()

            assert verified is False
            assert "Missing Istio components" in output

    def test_verify_install_exception(self) -> None:
        """Test verify_install raises IstioError on exception."""
        wrapper = IstioctlWrapper()

        with patch.object(wrapper, "_run_command") as mock_cmd:
            mock_cmd.side_effect = Exception("Unexpected error")

            with pytest.raises(IstioError) as exc_info:
                wrapper.verify_install()

            assert "Failed to verify Istio install" in str(exc_info.value)


class TestIstioctlCommandBuilding:
    """Tests for command building with various options."""

    def test_command_includes_all_flags(self) -> None:
        """Test command includes all specified flags."""
        wrapper = IstioctlWrapper(
            kubeconfig_path="/path/to/kubeconfig", context="production"
        )

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper._run_command(["analyze", "-n", "istio-system"])

            call_args = mock_run.call_args
            cmd = call_args[0][0]

            # Verify all components are present
            assert cmd[0] == "istioctl"
            assert "analyze" in cmd
            assert "-n" in cmd
            assert "istio-system" in cmd
            assert "--kubeconfig" in cmd
            assert "/path/to/kubeconfig" in cmd
            assert "--context" in cmd
            assert "production" in cmd

    def test_command_capture_output_settings(self) -> None:
        """Test command execution uses correct output capture settings."""
        wrapper = IstioctlWrapper()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper._run_command(["version"])

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["capture_output"] is True
            assert call_kwargs["text"] is True
