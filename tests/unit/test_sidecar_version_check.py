"""Unit tests for IstioSidecarVersionCheck.

This module tests the IstioSidecarVersionCheck which validates that Istio sidecar
proxy versions match the control plane version before and after upgrades.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import CheckContext
from guard.services.istio.checks.sidecar_version import IstioSidecarVersionCheck


@pytest.fixture
def sidecar_check() -> IstioSidecarVersionCheck:
    """Create IstioSidecarVersionCheck instance for testing.

    Returns:
        IstioSidecarVersionCheck instance
    """
    return IstioSidecarVersionCheck()


@pytest.fixture
def mock_kubernetes_provider() -> MagicMock:
    """Create mock KubernetesProvider for testing.

    Returns:
        Mock KubernetesProvider
    """
    provider = MagicMock()
    provider.get_namespaces = AsyncMock(return_value=["default", "app-namespace"])
    provider.get_pods = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def sample_check_context(mock_kubernetes_provider: MagicMock) -> CheckContext:
    """Create sample CheckContext with mocked dependencies.

    Args:
        mock_kubernetes_provider: Mock KubernetesProvider

    Returns:
        CheckContext instance
    """
    return CheckContext(
        cloud_provider=MagicMock(),
        kubernetes_provider=mock_kubernetes_provider,
        metrics_provider=MagicMock(),
        extra_context={},
    )


def create_mock_pod_with_sidecar(name: str, namespace: str, sidecar_image: str) -> MagicMock:
    """Create a mock pod with an Istio sidecar.

    Args:
        name: Pod name
        namespace: Pod namespace
        sidecar_image: Istio proxy container image

    Returns:
        Mock pod object
    """
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace

    # Create istio-proxy container
    proxy_container = MagicMock()
    proxy_container.name = "istio-proxy"
    proxy_container.image = sidecar_image

    # Create app container (non-sidecar)
    app_container = MagicMock()
    app_container.name = "app"
    app_container.image = "myapp:latest"

    pod.spec.containers = [app_container, proxy_container]

    return pod


def create_mock_pod_without_sidecar(name: str, namespace: str) -> MagicMock:
    """Create a mock pod without an Istio sidecar.

    Args:
        name: Pod name
        namespace: Pod namespace

    Returns:
        Mock pod object
    """
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace

    app_container = MagicMock()
    app_container.name = "app"
    app_container.image = "myapp:latest"

    pod.spec.containers = [app_container]

    return pod


class TestIstioSidecarVersionCheckProperties:
    """Test IstioSidecarVersionCheck properties."""

    def test_check_name(self, sidecar_check: IstioSidecarVersionCheck):
        """Test that check has correct name.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        assert sidecar_check.name == "istio_sidecar_version"

    def test_check_description(self, sidecar_check: IstioSidecarVersionCheck):
        """Test that check has proper description.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        expected_desc = "Validates Istio sidecar proxy versions match control plane"
        assert sidecar_check.description == expected_desc
        assert "sidecar" in sidecar_check.description.lower()
        assert "version" in sidecar_check.description.lower()

    def test_timeout_seconds_default(self, sidecar_check: IstioSidecarVersionCheck):
        """Test that check has default timeout.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        assert sidecar_check.timeout_seconds == 60
        assert sidecar_check.timeout_seconds > 0

    def test_is_critical_default(self, sidecar_check: IstioSidecarVersionCheck):
        """Test that check is critical by default.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        assert sidecar_check.is_critical is True


class TestVersionExtraction:
    """Test version extraction from container images."""

    def test_extract_version_from_standard_image(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from standard Istio image.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        image = "istio/proxyv2:1.20.0"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.20.0"

    def test_extract_version_from_dockerhub_image(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from Docker Hub image.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        image = "docker.io/istio/proxyv2:1.19.5"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.19.5"

    def test_extract_version_from_gcr_image(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from GCR image.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        image = "gcr.io/istio-release/proxyv2:1.18.2"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.18.2"

    def test_extract_version_from_distroless_image(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from distroless image.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        image = "docker.io/istio/proxyv2:1.20.0-distroless"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.20.0"

    def test_extract_version_from_custom_registry(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from custom registry.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        image = "my-registry.example.com:5000/istio/proxyv2:1.21.0"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.21.0"

    def test_extract_version_with_sha(self, sidecar_check: IstioSidecarVersionCheck):
        """Test version extraction from image with SHA tag.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        # Version should come from tag before SHA
        image = "istio/proxyv2:1.20.0@sha256:abc123"
        version = sidecar_check._extract_version_from_image(image)
        assert version == "1.20.0"

    def test_extract_version_returns_none_for_invalid_image(
        self, sidecar_check: IstioSidecarVersionCheck
    ):
        """Test that extraction returns None for invalid image format.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        invalid_images = [
            "istio/proxyv2:latest",
            "istio/proxyv2:v1.20",  # Missing patch version
            "myapp:1.0",  # Not a semver
            "no-tag-image",
        ]

        for image in invalid_images:
            version = sidecar_check._extract_version_from_image(image)
            assert version is None

    def test_extract_version_logs_failure(self, sidecar_check: IstioSidecarVersionCheck):
        """Test that failed extraction is logged.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
        """
        with patch("guard.services.istio.checks.sidecar_version.logger") as mock_logger:
            sidecar_check._extract_version_from_image("invalid:image")
            mock_logger.debug.assert_called_once_with(
                "version_extraction_failed", image="invalid:image"
            )


class TestSidecarVersionCheckExecution:
    """Test IstioSidecarVersionCheck execution."""

    @pytest.mark.asyncio
    async def test_execute_with_matching_versions(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution when all sidecars match expected version.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        # Create pods with matching versions
        pods_default = [
            create_mock_pod_with_sidecar(
                "pod1", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
            create_mock_pod_with_sidecar(
                "pod2", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
        ]

        pods_app = [
            create_mock_pod_with_sidecar(
                "pod3",
                "app-namespace",
                f"istio/proxyv2:{sample_cluster_config.current_istio_version}",
            ),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods_default, pods_app])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert isinstance(result, CheckResult)
        assert result.check_name == "istio_sidecar_version"
        assert result.passed is True
        assert "3 sidecars" in result.message
        assert "correct version" in result.message
        assert result.metrics["total_pods"] == 3

    @pytest.mark.asyncio
    async def test_execute_with_version_mismatches(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution when sidecars have version mismatches.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        # Create pods with mismatched versions
        pods = [
            create_mock_pod_with_sidecar(
                "pod1", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
            create_mock_pod_with_sidecar("pod2", "default", "istio/proxyv2:1.18.0"),  # Mismatch
            create_mock_pod_with_sidecar("pod3", "default", "istio/proxyv2:1.17.5"),  # Mismatch
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is False
        assert "2 sidecar version mismatches" in result.message
        assert result.metrics["total_pods"] == 3
        assert result.metrics["mismatches"] == 2

    @pytest.mark.asyncio
    async def test_execute_with_no_sidecar_pods(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution when no pods have sidecars.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        # Create pods without sidecars
        pods = [
            create_mock_pod_without_sidecar("pod1", "default"),
            create_mock_pod_without_sidecar("pod2", "default"),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is True
        assert result.metrics["total_pods"] == 0
        assert "0 sidecars" in result.message

    @pytest.mark.asyncio
    async def test_execute_with_no_istio_namespaces(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution when no namespaces have istio-injection enabled.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        mock_kubernetes_provider.get_namespaces = AsyncMock(return_value=[])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is True
        assert result.metrics["total_pods"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_mixed_pods(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution with mix of sidecar and non-sidecar pods.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pods = [
            create_mock_pod_with_sidecar(
                "pod1", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
            create_mock_pod_without_sidecar("pod2", "default"),
            create_mock_pod_with_sidecar(
                "pod3", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is True
        assert result.metrics["total_pods"] == 2  # Only counts pods with sidecars


class TestSidecarVersionCheckWithInvalidVersions:
    """Test IstioSidecarVersionCheck with invalid version formats."""

    @pytest.mark.asyncio
    async def test_execute_ignores_pods_with_invalid_version_format(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that pods with invalid version format are ignored.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pods = [
            create_mock_pod_with_sidecar(
                "pod1", "default", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
            create_mock_pod_with_sidecar("pod2", "default", "istio/proxyv2:latest"),
            create_mock_pod_with_sidecar("pod3", "default", "istio/proxyv2:dev-build"),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        # Only pod1 should be counted (valid version)
        assert result.passed is True
        assert result.metrics["total_pods"] == 3

    @pytest.mark.asyncio
    async def test_execute_with_null_version_extraction(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution when version extraction returns None.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pods = [
            create_mock_pod_with_sidecar("pod1", "default", "istio/proxyv2:invalid-tag"),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        # Pod counted but no version mismatch (None != expected doesn't trigger mismatch)
        assert result.passed is True
        assert result.metrics["total_pods"] == 1


class TestSidecarVersionCheckErrorHandling:
    """Test IstioSidecarVersionCheck error handling."""

    @pytest.mark.asyncio
    async def test_execute_handles_kubernetes_exception(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that execution handles Kubernetes exceptions gracefully.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        mock_kubernetes_provider.get_namespaces.side_effect = Exception("K8s API error")

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert isinstance(result, CheckResult)
        assert result.check_name == "istio_sidecar_version"
        assert result.passed is False
        assert "failed" in result.message.lower()
        assert "K8s API error" in result.message
        assert result.metrics == {}

    @pytest.mark.asyncio
    async def test_execute_handles_get_pods_exception(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that execution handles get_pods exceptions gracefully.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        mock_kubernetes_provider.get_namespaces = AsyncMock(return_value=["default"])
        mock_kubernetes_provider.get_pods.side_effect = Exception("Failed to get pods")

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is False
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_execute_logs_errors(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that execution logs errors appropriately.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        mock_kubernetes_provider.get_namespaces.side_effect = Exception("Test error")

        with patch("guard.services.istio.checks.sidecar_version.logger") as mock_logger:
            result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

            # Verify error was logged
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert call_args[0][0] == "sidecar_version_check_failed"
            assert call_args[1]["cluster_id"] == sample_cluster_config.cluster_id
            assert "Test error" in call_args[1]["error"]

            assert result.passed is False


class TestSidecarVersionCheckLogging:
    """Test IstioSidecarVersionCheck logging."""

    @pytest.mark.asyncio
    async def test_execute_logs_version_mismatches(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that version mismatches are logged with warnings.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pods = [
            create_mock_pod_with_sidecar("pod1", "default", "istio/proxyv2:1.18.0"),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods, []])

        with patch("guard.services.istio.checks.sidecar_version.logger") as mock_logger:
            await sidecar_check.execute(sample_cluster_config, sample_check_context)

            # Verify warning was logged for mismatch
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "sidecar_version_mismatch"
            assert "default/pod1" in call_args[1]["pod"]
            assert call_args[1]["expected"] == sample_cluster_config.current_istio_version
            assert call_args[1]["actual"] == "1.18.0"

    @pytest.mark.asyncio
    async def test_execute_logs_start(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that check start is logged.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        with patch("guard.services.istio.checks.sidecar_version.logger") as mock_logger:
            await sidecar_check.execute(sample_cluster_config, sample_check_context)

            # Verify info log was called at start
            mock_logger.info.assert_called_once_with(
                "checking_sidecar_versions", cluster_id=sample_cluster_config.cluster_id
            )


class TestSidecarVersionCheckEdgeCases:
    """Test IstioSidecarVersionCheck edge cases."""

    @pytest.mark.asyncio
    async def test_execute_with_pod_missing_spec(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution with pod missing spec attribute.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pod = MagicMock()
        pod.metadata.name = "pod1"
        delattr(pod, "spec")  # Remove spec attribute

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[[pod], []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        # Should not crash, just skip the pod
        assert result.passed is True
        assert result.metrics["total_pods"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_pod_missing_containers(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution with pod spec missing containers attribute.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        pod = MagicMock()
        pod.metadata.name = "pod1"
        pod.spec = MagicMock()
        delattr(pod.spec, "containers")  # Remove containers attribute

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[[pod], []])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        # Should not crash, just skip the pod
        assert result.passed is True
        assert result.metrics["total_pods"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_multiple_namespaces(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test execution across multiple namespaces.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        mock_kubernetes_provider.get_namespaces = AsyncMock(return_value=["ns1", "ns2", "ns3"])

        pods_ns1 = [
            create_mock_pod_with_sidecar(
                "pod1", "ns1", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
        ]
        pods_ns2 = [
            create_mock_pod_with_sidecar(
                "pod2", "ns2", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
        ]
        pods_ns3 = [
            create_mock_pod_with_sidecar(
                "pod3", "ns3", f"istio/proxyv2:{sample_cluster_config.current_istio_version}"
            ),
        ]

        mock_kubernetes_provider.get_pods = AsyncMock(side_effect=[pods_ns1, pods_ns2, pods_ns3])

        result = await sidecar_check.execute(sample_cluster_config, sample_check_context)

        assert result.passed is True
        assert result.metrics["total_pods"] == 3

        # Verify get_pods was called for each namespace
        assert mock_kubernetes_provider.get_pods.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_verifies_label_selector(
        self,
        sidecar_check: IstioSidecarVersionCheck,
        sample_cluster_config: ClusterConfig,
        sample_check_context: CheckContext,
        mock_kubernetes_provider: MagicMock,
    ):
        """Test that get_namespaces is called with correct label selector.

        Args:
            sidecar_check: IstioSidecarVersionCheck instance
            sample_cluster_config: Sample cluster configuration
            sample_check_context: CheckContext with mocked dependencies
            mock_kubernetes_provider: Mock KubernetesProvider
        """
        await sidecar_check.execute(sample_cluster_config, sample_check_context)

        # Verify get_namespaces was called with istio-injection=enabled label
        mock_kubernetes_provider.get_namespaces.assert_called_once_with(
            label_selector="istio-injection=enabled"
        )
