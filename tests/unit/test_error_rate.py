"""Unit tests for IstioErrorRateValidator.

Tests the Istio error rate validator for comparing error rates before and after upgrade.
All external dependencies are mocked to ensure tests are isolated and fast.
"""

from datetime import datetime

import pytest

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult
from guard.services.istio.validators.error_rate import IstioErrorRateValidator


@pytest.fixture
def validator() -> IstioErrorRateValidator:
    """Create an IstioErrorRateValidator instance."""
    return IstioErrorRateValidator()


@pytest.fixture
def baseline_snapshot() -> MetricsSnapshot:
    """Create a baseline metrics snapshot with normal error rates."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.error.5xx.rate": 0.0005,  # 0.05%
            "istio.request.total.rate": 10000.0,  # 10k req/s
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_healthy() -> MetricsSnapshot:
    """Create a current metrics snapshot with healthy error rates."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.error.5xx.rate": 0.0006,  # Slight increase, still healthy
            "istio.request.total.rate": 10500.0,  # Slight increase
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_high_errors() -> MetricsSnapshot:
    """Create a current metrics snapshot with high error rates."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.error.5xx.rate": 0.002,  # Above threshold
            "istio.request.total.rate": 10000.0,
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_increased_errors() -> MetricsSnapshot:
    """Create a current metrics snapshot with significantly increased errors."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.error.5xx.rate": 0.0012,  # More than 2x increase
            "istio.request.total.rate": 10000.0,
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_dropped_traffic() -> MetricsSnapshot:
    """Create a current metrics snapshot with dropped traffic."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.error.5xx.rate": 0.0005,
            "istio.request.total.rate": 7000.0,  # 30% drop
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def thresholds() -> ValidationThresholds:
    """Create validation thresholds."""
    return ValidationThresholds(
        error_rate_max=0.001,  # 0.1% max
        latency_increase_percent=10.0,
    )


class TestIstioErrorRateValidatorProperties:
    """Tests for validator properties."""

    def test_name_property(self, validator: IstioErrorRateValidator) -> None:
        """Test that validator has correct name."""
        assert validator.name == "istio_error_rate"

    def test_description_property(self, validator: IstioErrorRateValidator) -> None:
        """Test that validator has description."""
        assert validator.description
        assert "5xx" in validator.description.lower()

    def test_is_critical_property(self, validator: IstioErrorRateValidator) -> None:
        """Test that validator is critical by default."""
        assert validator.is_critical is True

    def test_timeout_property(self, validator: IstioErrorRateValidator) -> None:
        """Test that validator has reasonable timeout."""
        assert validator.timeout_seconds == 60


class TestIstioErrorRateValidatorGetRequiredMetrics:
    """Tests for get_required_metrics method."""

    @pytest.mark.asyncio
    async def test_get_required_metrics(self, validator: IstioErrorRateValidator) -> None:
        """Test that validator returns correct required metrics."""
        metrics = await validator.get_required_metrics()

        assert isinstance(metrics, list)
        assert "istio.request.error.5xx.rate" in metrics
        assert "istio.request.total.rate" in metrics
        assert len(metrics) == 2


class TestIstioErrorRateValidatorValidate:
    """Tests for validate method."""

    @pytest.mark.asyncio
    async def test_validate_healthy_metrics_pass(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation passes with healthy metrics."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )

        assert isinstance(result, ValidationResult)
        assert result.passed is True
        assert len(result.violations) == 0
        assert result.cluster_id == sample_cluster_config.cluster_id
        assert result.validator_name == "istio_error_rate"

    @pytest.mark.asyncio
    async def test_validate_error_rate_exceeds_maximum(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_high_errors: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when error rate exceeds maximum threshold."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_high_errors,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) >= 1
        assert any("exceeds maximum" in v for v in result.violations)

    @pytest.mark.asyncio
    async def test_validate_error_rate_increased_significantly(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_increased_errors: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when error rate increases significantly (>2x)."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_increased_errors,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) >= 1
        assert any("increased" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_validate_request_rate_dropped_significantly(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_dropped_traffic: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when request rate drops significantly (>20%)."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_dropped_traffic,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) >= 1
        assert any("dropped" in v.lower() for v in result.violations)

    @pytest.mark.asyncio
    async def test_validate_with_zero_baseline_errors(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles zero baseline errors correctly."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.0,  # No errors
                "istio.request.total.rate": 10000.0,
            },
            tags={},
        )

        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.0008,  # Some errors now
                "istio.request.total.rate": 10000.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current,
            thresholds=thresholds,
        )

        # Should pass since errors are still below max threshold
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_with_missing_baseline_metrics(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles missing baseline metrics gracefully."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={},  # No metrics
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )

        # Should still validate, using 0 for missing baseline
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_with_missing_current_metrics(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles missing current metrics gracefully."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={},  # No metrics
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Should still validate, using 0 for missing current
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_with_zero_baseline_requests(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles zero baseline requests correctly."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.0,
                "istio.request.total.rate": 0.0,  # No traffic
            },
            tags={},
        )

        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.0005,
                "istio.request.total.rate": 10000.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current,
            thresholds=thresholds,
        )

        # Should pass - no drop percentage calculation when baseline is 0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_error_rate_exactly_at_threshold(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation behavior when error rate is exactly at threshold."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.001,  # Exactly at threshold
                "istio.request.total.rate": 10000.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Exactly at threshold should pass (not exceeding)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_request_rate_exactly_20_percent_drop(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation behavior when request rate drops exactly 20%."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.0005,
                "istio.request.total.rate": 8000.0,  # Exactly 20% drop
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Exactly 20% should pass (not exceeding threshold)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_multiple_violations(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation captures multiple violations."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.002,  # Exceeds max and increased
                "istio.request.total.rate": 7000.0,  # Dropped >20%
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        assert result.passed is False
        # Should have multiple violations
        assert len(result.violations) >= 2

    @pytest.mark.asyncio
    async def test_validate_includes_metrics_in_result(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test that validation result includes current metrics."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )

        assert result.metrics == current_snapshot_healthy.metrics

    @pytest.mark.asyncio
    async def test_validate_timestamp_is_recent(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test that validation result has recent timestamp."""
        before = datetime.utcnow()
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )
        after = datetime.utcnow()

        assert before <= result.timestamp <= after

    @pytest.mark.asyncio
    async def test_validate_error_increase_just_under_2x_threshold(
        self,
        validator: IstioErrorRateValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation passes when error increase is just under 2x threshold."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.error.5xx.rate": 0.00099,  # 1.98x increase (under 2x)
                "istio.request.total.rate": 10000.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Should pass since increase is under 2x
        assert result.passed is True
