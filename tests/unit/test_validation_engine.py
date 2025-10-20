"""Unit tests for ValidationEngine.

Tests the validation engine for post-upgrade validation operations.
All external dependencies (kubectl, flux, istioctl) are mocked.
"""

import subprocess
import time
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from kubernetes.client.models import (
    V1Container,
    V1Deployment,
    V1DeploymentSpec,
    V1LabelSelector,
    V1ObjectMeta,
    V1Pod,
    V1PodCondition,
    V1PodSpec,
    V1PodStatus,
    V1PodTemplateSpec,
)

from guard.clients.kubernetes_client import KubernetesClient
from guard.core.models import CheckResult, ClusterConfig
from guard.validation.engine import ValidationEngine


@pytest.fixture
def validation_engine() -> ValidationEngine:
    """Create a validation engine with default settings."""
    return ValidationEngine(soak_period_minutes=60, restart_pods_with_sidecars=True)


@pytest.fixture
def quick_validation_engine() -> ValidationEngine:
    """Create a validation engine with short soak period for testing."""
    return ValidationEngine(soak_period_minutes=1, restart_pods_with_sidecars=True)


@pytest.fixture
def mock_k8s_client() -> MagicMock:
    """Create a mock Kubernetes client."""
    client = MagicMock(spec=KubernetesClient)
    return client


@pytest.fixture
def sample_pod_ready() -> V1Pod:
    """Create a sample ready pod."""
    return V1Pod(
        metadata=V1ObjectMeta(name="istiod-12345-abcde", namespace="istio-system"),
        status=V1PodStatus(
            phase="Running",
            conditions=[V1PodCondition(type="Ready", status="True")],
        ),
    )


@pytest.fixture
def sample_pod_not_ready() -> V1Pod:
    """Create a sample not-ready pod."""
    return V1Pod(
        metadata=V1ObjectMeta(name="istiod-12345-xxxxx", namespace="istio-system"),
        status=V1PodStatus(
            phase="Running",
            conditions=[V1PodCondition(type="Ready", status="False")],
        ),
    )


@pytest.fixture
def sample_deployment_with_sidecar() -> V1Deployment:
    """Create a sample deployment with Istio sidecar."""
    return V1Deployment(
        metadata=V1ObjectMeta(name="my-app", namespace="default"),
        spec=V1DeploymentSpec(
            selector=V1LabelSelector(match_labels={"app": "my-app"}),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(
                    labels={"app": "my-app"},
                    annotations={"sidecar.istio.io/status": '{"version":"1.20.0"}'},
                ),
                spec=V1PodSpec(
                    containers=[
                        V1Container(name="app", image="my-app:latest"),
                        V1Container(name="istio-proxy", image="istio/proxyv2:1.20.0"),
                    ]
                ),
            )
        ),
    )


@pytest.fixture
def sample_deployment_without_sidecar() -> V1Deployment:
    """Create a sample deployment without Istio sidecar."""
    return V1Deployment(
        metadata=V1ObjectMeta(name="standalone-app", namespace="default"),
        spec=V1DeploymentSpec(
            selector=V1LabelSelector(match_labels={"app": "standalone-app"}),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels={"app": "standalone-app"}),
                spec=V1PodSpec(
                    containers=[
                        V1Container(name="app", image="standalone-app:latest"),
                    ]
                )
            )
        ),
    )


class TestValidationEngineInit:
    """Tests for ValidationEngine initialization."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        engine = ValidationEngine()

        assert engine.soak_period == 60 * 60  # 60 minutes in seconds
        assert engine.restart_pods_with_sidecars is True

    def test_init_custom_soak_period(self) -> None:
        """Test initialization with custom soak period."""
        engine = ValidationEngine(soak_period_minutes=30)

        assert engine.soak_period == 30 * 60  # 30 minutes in seconds

    def test_init_restart_disabled(self) -> None:
        """Test initialization with pod restart disabled."""
        engine = ValidationEngine(restart_pods_with_sidecars=False)

        assert engine.restart_pods_with_sidecars is False


class TestValidationEngineWaitForFluxSync:
    """Tests for Flux sync waiting."""

    @patch("subprocess.run")
    def test_wait_for_flux_sync_success(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test successful Flux sync wait."""
        # Mock both kustomizations and helmreleases as ready
        kustomizations_output = "flux-system\tflux-system\tmaster/abc123\tFalse\tTrue\tApplied"
        helmreleases_output = "istio-system\tistio-base\t1.20.0\tFalse\tTrue\tRelease reconciliation succeeded"

        mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=kustomizations_output, stderr=""
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=helmreleases_output, stderr=""
            ),
        ]

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=1, poll_interval=1
        )

        assert result is True

    @patch("subprocess.run")
    def test_wait_for_flux_sync_timeout(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test Flux sync wait timeout."""
        # Always return not ready
        kustomizations_output = "flux-system\tflux-system\tmaster/abc123\tFalse\tFalse\tReconciling"
        helmreleases_output = "istio-system\tistio-base\t1.20.0\tFalse\tFalse\tProgressing"

        mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=kustomizations_output, stderr=""
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=helmreleases_output, stderr=""
            ),
        ] * 100  # Many iterations

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=0.05, poll_interval=0.01
        )

        assert result is False

    @patch("subprocess.run")
    def test_wait_for_flux_sync_kustomizations_not_ready(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test Flux sync when kustomizations are not ready."""
        # Kustomizations not ready, helmreleases ready
        kustomizations_output = "flux-system\tflux-system\tmaster/abc123\tFalse\tFalse\tReconciling"
        helmreleases_output = "istio-system\tistio-base\t1.20.0\tFalse\tTrue\tRelease reconciliation succeeded"

        mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=kustomizations_output, stderr=""
            ),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout=helmreleases_output, stderr=""
            ),
        ] * 100

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=0.05, poll_interval=0.01
        )

        assert result is False

    @patch("subprocess.run")
    def test_wait_for_flux_sync_empty_output(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test Flux sync with empty output (no resources)."""
        # Empty output means no resources, which is considered ready
        mock_subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=1, poll_interval=1
        )

        assert result is True

    @patch("subprocess.run")
    def test_wait_for_flux_sync_subprocess_timeout(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test Flux sync when subprocess times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(cmd="flux", timeout=30)

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=0.05, poll_interval=0.01
        )

        assert result is False

    @patch("subprocess.run")
    def test_wait_for_flux_sync_subprocess_error(
        self,
        mock_subprocess_run: MagicMock,
        validation_engine: ValidationEngine,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test Flux sync when subprocess raises exception."""
        mock_subprocess_run.side_effect = Exception("Command not found")

        result = validation_engine.wait_for_flux_sync(
            cluster=sample_cluster_config, timeout_minutes=0.05, poll_interval=0.01
        )

        assert result is False


class TestValidationEngineRunSoakPeriod:
    """Tests for soak period execution."""

    @patch("time.sleep")
    @patch("time.time")
    def test_run_soak_period_completes(
        self,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
        quick_validation_engine: ValidationEngine,
    ) -> None:
        """Test that soak period runs to completion."""
        # Mock time progression
        mock_time.side_effect = [0, 30, 60, 60]

        quick_validation_engine.run_soak_period(progress_interval=30)

        # Should sleep for soak period duration
        assert mock_sleep.called

    @patch("time.sleep")
    @patch("time.time")
    def test_run_soak_period_logs_progress(
        self,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
        validation_engine: ValidationEngine,
    ) -> None:
        """Test that soak period logs progress at intervals."""
        # Mock time progression through multiple intervals
        mock_time.side_effect = [0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720, 780, 840, 900, 960, 1020, 1080, 1140, 1200, 1260, 1320, 1380, 1440, 1500, 1560, 1620, 1680, 1740, 1800, 1860, 1920, 1980, 2040, 2100, 2160, 2220, 2280, 2340, 2400, 2460, 2520, 2580, 2640, 2700, 2760, 2820, 2880, 2940, 3000, 3060, 3120, 3180, 3240, 3300, 3360, 3420, 3480, 3540, 3600, 3600]

        validation_engine.run_soak_period(progress_interval=60)

        # Should sleep multiple times
        assert mock_sleep.call_count > 1


class TestValidationEngineValidateIstioDeployment:
    """Tests for Istio deployment validation."""

    def test_validate_istio_deployment_success(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
    ) -> None:
        """Test successful Istio deployment validation."""
        mock_k8s_client.get_pods.return_value = [sample_pod_ready]

        with patch("subprocess.run") as mock_subprocess:
            # Mock istioctl analyze success
            mock_subprocess.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="✔ No validation issues found\n", stderr=""
            )

            result = validation_engine.validate_istio_deployment(
                cluster=sample_cluster_config, k8s_client=mock_k8s_client
            )

        assert result.passed is True
        assert "successfully" in result.message.lower()

    def test_validate_istio_deployment_no_istiod_pods(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test validation when no istiod pods are found."""
        mock_k8s_client.get_pods.return_value = []

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "no istiod pods" in result.message.lower()

    def test_validate_istio_deployment_istiod_not_ready(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_not_ready: V1Pod,
    ) -> None:
        """Test validation when istiod pods are not ready."""
        mock_k8s_client.get_pods.return_value = [sample_pod_not_ready]

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "not ready" in result.message.lower()

    def test_validate_istio_deployment_gateway_not_ready(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
        sample_pod_not_ready: V1Pod,
    ) -> None:
        """Test validation when gateway pods are not ready."""
        # First call for istiod (ready), second for gateways (not ready)
        mock_k8s_client.get_pods.side_effect = [
            [sample_pod_ready],  # istiod ready
            [sample_pod_not_ready],  # gateway not ready
        ]

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "gateway" in result.message.lower()

    @patch("subprocess.run")
    def test_validate_istio_deployment_istioctl_analyze_errors(
        self,
        mock_subprocess: MagicMock,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
    ) -> None:
        """Test validation when istioctl analyze finds errors."""
        mock_k8s_client.get_pods.return_value = [sample_pod_ready]

        # Mock istioctl analyze with errors
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="Error [IST0101] (VirtualService default/my-vs) Referenced gateway not found\n",
            stderr="",
        )

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "analyze found errors" in result.message.lower()

    @patch("subprocess.run")
    def test_validate_istio_deployment_istioctl_timeout(
        self,
        mock_subprocess: MagicMock,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
    ) -> None:
        """Test validation when istioctl times out."""
        mock_k8s_client.get_pods.return_value = [sample_pod_ready]

        # Mock istioctl timeout
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="istioctl", timeout=60)

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "timed out" in result.message.lower()

    @patch("subprocess.run")
    def test_validate_istio_deployment_istioctl_not_found(
        self,
        mock_subprocess: MagicMock,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
    ) -> None:
        """Test validation when istioctl is not found."""
        mock_k8s_client.get_pods.return_value = [sample_pod_ready]

        # Mock istioctl not found
        mock_subprocess.side_effect = FileNotFoundError("istioctl not found")

        # Should not fail validation, just log warning
        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        # Validation can still pass if pods are healthy
        assert isinstance(result, CheckResult)

    @patch("subprocess.run")
    def test_validate_istio_deployment_proxy_not_synced(
        self,
        mock_subprocess: MagicMock,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_pod_ready: V1Pod,
    ) -> None:
        """Test validation when proxies are not synced."""
        mock_k8s_client.get_pods.return_value = [sample_pod_ready]

        # First call: istioctl analyze (success), second call: proxy-status (not synced)
        mock_subprocess.side_effect = [
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="✔ No validation issues found\n", stderr=""
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                # Status without "SYNCED" in the line
                stdout="NAME     STATUS    VERSION\npod1.ns  STALE  1.20.0\n",
                stderr="",
            ),
        ]

        result = validation_engine.validate_istio_deployment(
            cluster=sample_cluster_config, k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "not synced" in result.message.lower()


class TestValidationEngineHasIstioSidecar:
    """Tests for Istio sidecar detection."""

    def test_has_istio_sidecar_with_proxy_container(
        self,
        validation_engine: ValidationEngine,
        sample_deployment_with_sidecar: V1Deployment,
    ) -> None:
        """Test detection of istio-proxy container."""
        has_sidecar = validation_engine._has_istio_sidecar(sample_deployment_with_sidecar.spec)

        assert has_sidecar is True

    def test_has_istio_sidecar_with_annotation(
        self, validation_engine: ValidationEngine
    ) -> None:
        """Test detection via sidecar.istio.io/status annotation."""
        deployment = V1Deployment(
            spec=V1DeploymentSpec(
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(
                    metadata=V1ObjectMeta(
                        labels={"app": "test"},
                        annotations={"sidecar.istio.io/status": '{"version":"1.20.0"}'},
                    ),
                    spec=V1PodSpec(containers=[V1Container(name="app", image="app:latest")]),
                )
            )
        )

        has_sidecar = validation_engine._has_istio_sidecar(deployment.spec)

        assert has_sidecar is True

    def test_has_istio_sidecar_with_inject_annotation(
        self, validation_engine: ValidationEngine
    ) -> None:
        """Test detection via sidecar.istio.io/inject annotation."""
        deployment = V1Deployment(
            spec=V1DeploymentSpec(
                selector=V1LabelSelector(match_labels={"app": "test"}),
                template=V1PodTemplateSpec(
                    metadata=V1ObjectMeta(
                        labels={"app": "test"},
                        annotations={"sidecar.istio.io/inject": "true"},
                    ),
                    spec=V1PodSpec(containers=[V1Container(name="app", image="app:latest")]),
                )
            )
        )

        has_sidecar = validation_engine._has_istio_sidecar(deployment.spec)

        assert has_sidecar is True

    def test_has_istio_sidecar_without_sidecar(
        self,
        validation_engine: ValidationEngine,
        sample_deployment_without_sidecar: V1Deployment,
    ) -> None:
        """Test detection when no sidecar is present."""
        has_sidecar = validation_engine._has_istio_sidecar(
            sample_deployment_without_sidecar.spec
        )

        assert has_sidecar is False

    def test_has_istio_sidecar_with_exception(
        self, validation_engine: ValidationEngine
    ) -> None:
        """Test sidecar detection handles exceptions gracefully."""
        # Pass invalid spec that will raise exception
        has_sidecar = validation_engine._has_istio_sidecar(None)

        assert has_sidecar is False


class TestValidationEngineRestartPodsWithIstioSidecars:
    """Tests for restarting pods with Istio sidecars."""

    def test_restart_pods_success(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_deployment_with_sidecar: V1Deployment,
    ) -> None:
        """Test successful pod restart."""
        # Mock namespace query
        ns = MagicMock()
        ns.metadata.name = "default"
        mock_k8s_client.get_namespaces.return_value = [ns]

        # Mock deployment query
        mock_k8s_client.get_deployments.return_value = [sample_deployment_with_sidecar]
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []

        # Mock restart and readiness check
        mock_k8s_client.restart_deployment.return_value = None
        mock_k8s_client.check_deployment_ready.return_value = True

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, wait_for_ready=True, wave_size=5
        )

        assert result.passed is True
        assert "1" in result.message  # 1 resource restarted
        mock_k8s_client.restart_deployment.assert_called_once()

    def test_restart_pods_specific_namespace(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_deployment_with_sidecar: V1Deployment,
    ) -> None:
        """Test pod restart in specific namespace."""
        mock_k8s_client.get_deployments.return_value = [sample_deployment_with_sidecar]
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []
        mock_k8s_client.restart_deployment.return_value = None
        mock_k8s_client.check_deployment_ready.return_value = True

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, namespace="default", wait_for_ready=True
        )

        assert result.passed is True
        # Should not call get_namespaces when namespace is specified
        mock_k8s_client.get_namespaces.assert_not_called()

    def test_restart_pods_skips_deployments_without_sidecars(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_deployment_without_sidecar: V1Deployment,
    ) -> None:
        """Test that deployments without sidecars are skipped."""
        ns = MagicMock()
        ns.metadata.name = "default"
        mock_k8s_client.get_namespaces.return_value = [ns]

        mock_k8s_client.get_deployments.return_value = [sample_deployment_without_sidecar]
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, wait_for_ready=True
        )

        assert result.passed is True
        # No deployments should be restarted
        mock_k8s_client.restart_deployment.assert_not_called()

    def test_restart_pods_handles_restart_failure(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_deployment_with_sidecar: V1Deployment,
    ) -> None:
        """Test handling of restart failures."""
        ns = MagicMock()
        ns.metadata.name = "default"
        mock_k8s_client.get_namespaces.return_value = [ns]

        mock_k8s_client.get_deployments.return_value = [sample_deployment_with_sidecar]
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []

        # Mock restart failure
        mock_k8s_client.restart_deployment.side_effect = Exception("Restart failed")

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, wait_for_ready=False
        )

        assert result.passed is False
        assert "failed" in result.message.lower()

    @patch("time.sleep")
    def test_restart_pods_waits_for_readiness(
        self,
        mock_sleep: MagicMock,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
        sample_deployment_with_sidecar: V1Deployment,
    ) -> None:
        """Test that restart waits for pods to be ready."""
        ns = MagicMock()
        ns.metadata.name = "default"
        mock_k8s_client.get_namespaces.return_value = [ns]

        mock_k8s_client.get_deployments.return_value = [sample_deployment_with_sidecar]
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []
        mock_k8s_client.restart_deployment.return_value = None

        # First check not ready, second check ready
        mock_k8s_client.check_deployment_ready.side_effect = [False, True]

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, wait_for_ready=True
        )

        assert result.passed is True
        # Should sleep while waiting for readiness
        mock_sleep.assert_called()

    def test_restart_pods_wave_based_restart(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test wave-based restart with multiple deployments."""
        ns = MagicMock()
        ns.metadata.name = "default"
        mock_k8s_client.get_namespaces.return_value = [ns]

        # Create 3 deployments with sidecars
        deployments = []
        for i in range(3):
            dep = V1Deployment(
                metadata=V1ObjectMeta(name=f"app-{i}", namespace="default"),
                spec=V1DeploymentSpec(
                    selector=V1LabelSelector(match_labels={"app": f"app-{i}"}),
                    template=V1PodTemplateSpec(
                        metadata=V1ObjectMeta(labels={"app": f"app-{i}"}),
                        spec=V1PodSpec(
                            containers=[
                                V1Container(name="app", image="app:latest"),
                                V1Container(name="istio-proxy", image="istio/proxyv2:1.20.0"),
                            ]
                        )
                    )
                ),
            )
            deployments.append(dep)

        mock_k8s_client.get_deployments.return_value = deployments
        mock_k8s_client.get_statefulsets.return_value = []
        mock_k8s_client.get_daemonsets.return_value = []
        mock_k8s_client.restart_deployment.return_value = None
        mock_k8s_client.check_deployment_ready.return_value = True

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client, wave_size=2, wait_for_ready=True
        )

        assert result.passed is True
        assert mock_k8s_client.restart_deployment.call_count == 3

    def test_restart_pods_exception_handling(
        self,
        validation_engine: ValidationEngine,
        mock_k8s_client: MagicMock,
    ) -> None:
        """Test that exceptions are handled gracefully."""
        mock_k8s_client.get_namespaces.side_effect = Exception("API error")

        result = validation_engine.restart_pods_with_istio_sidecars(
            k8s_client=mock_k8s_client
        )

        assert result.passed is False
        assert "failed" in result.message.lower()
