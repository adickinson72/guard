"""Unit tests for IstioLatencyValidator.

Tests the Istio latency validator for comparing latency before and after upgrade.
All external dependencies are mocked to ensure tests are isolated and fast.
"""

from datetime import datetime

import pytest

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult
from guard.services.istio.validators.latency import IstioLatencyValidator


@pytest.fixture
def validator() -> IstioLatencyValidator:
    """Create an IstioLatencyValidator instance."""
    return IstioLatencyValidator()


@pytest.fixture
def baseline_snapshot() -> MetricsSnapshot:
    """Create a baseline metrics snapshot with normal latency."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 100.0,  # 100ms p95
            "istio.request.latency.p99": 200.0,  # 200ms p99
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_healthy() -> MetricsSnapshot:
    """Create a current metrics snapshot with healthy latency (minor increase)."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 105.0,  # 5% increase
            "istio.request.latency.p99": 210.0,  # 5% increase
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_p95_degraded() -> MetricsSnapshot:
    """Create a current metrics snapshot with degraded p95 latency."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 115.0,  # 15% increase (exceeds 10% threshold)
            "istio.request.latency.p99": 210.0,  # 5% increase (within threshold)
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_p99_degraded() -> MetricsSnapshot:
    """Create a current metrics snapshot with degraded p99 latency."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 105.0,  # 5% increase (within threshold)
            "istio.request.latency.p99": 235.0,  # 17.5% increase (exceeds 15% threshold)
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def current_snapshot_both_degraded() -> MetricsSnapshot:
    """Create a current metrics snapshot with both p95 and p99 degraded."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 120.0,  # 20% increase
            "istio.request.latency.p99": 250.0,  # 25% increase
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def thresholds() -> ValidationThresholds:
    """Create validation thresholds."""
    return ValidationThresholds(
        latency_p95_increase_percent=10.0,
        latency_p99_increase_percent=10.0,
    )


@pytest.fixture
def strict_thresholds() -> ValidationThresholds:
    """Create strict validation thresholds."""
    return ValidationThresholds(
        latency_p95_increase_percent=5.0,
        latency_p99_increase_percent=5.0,
    )


class TestIstioLatencyValidatorProperties:
    """Tests for validator properties."""

    def test_name_property(self, validator: IstioLatencyValidator) -> None:
        """Test that validator has correct name."""
        assert validator.name == "istio_latency"

    def test_description_property(self, validator: IstioLatencyValidator) -> None:
        """Test that validator has description."""
        assert validator.description
        assert "p95" in validator.description.lower()

    def test_is_critical_property(self, validator: IstioLatencyValidator) -> None:
        """Test that validator is critical by default."""
        assert validator.is_critical is True

    def test_timeout_property(self, validator: IstioLatencyValidator) -> None:
        """Test that validator has reasonable timeout."""
        assert validator.timeout_seconds == 60


class TestIstioLatencyValidatorGetRequiredMetrics:
    """Tests for get_required_metrics method."""

    @pytest.mark.asyncio
    async def test_get_required_metrics(self, validator: IstioLatencyValidator) -> None:
        """Test that validator returns correct required metrics."""
        metrics = await validator.get_required_metrics()

        assert isinstance(metrics, list)
        assert "istio.request.latency.p95" in metrics
        assert "istio.request.latency.p99" in metrics
        assert len(metrics) == 2


class TestIstioLatencyValidatorValidate:
    """Tests for validate method."""

    @pytest.mark.asyncio
    async def test_validate_healthy_metrics_pass(
        self,
        validator: IstioLatencyValidator,
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
        assert result.validator_name == "istio_latency"

    @pytest.mark.asyncio
    async def test_validate_p95_exceeds_threshold(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_p95_degraded: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when p95 latency increase exceeds threshold."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_p95_degraded,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) == 1
        assert "p95" in result.violations[0].lower()
        assert "15.0%" in result.violations[0]  # Should show actual increase

    @pytest.mark.asyncio
    async def test_validate_p99_exceeds_threshold(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_p99_degraded: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when p99 latency increase exceeds threshold."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_p99_degraded,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) == 1
        assert "p99" in result.violations[0].lower()
        assert "17.5%" in result.violations[0]  # Should show actual increase

    @pytest.mark.asyncio
    async def test_validate_both_percentiles_exceed_threshold(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_both_degraded: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation fails when both p95 and p99 exceed thresholds."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_both_degraded,
            thresholds=thresholds,
        )

        assert result.passed is False
        assert len(result.violations) == 2
        # Should have violations for both p95 and p99
        violations_text = " ".join(result.violations).lower()
        assert "p95" in violations_text
        assert "p99" in violations_text

    @pytest.mark.asyncio
    async def test_validate_with_zero_baseline_p95(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles zero baseline p95 gracefully."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 0.0,  # Zero baseline
                "istio.request.latency.p99": 200.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )

        # Should pass - no percentage calculation for zero baseline
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_with_zero_baseline_p99(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        current_snapshot_healthy: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles zero baseline p99 gracefully."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 100.0,
                "istio.request.latency.p99": 0.0,  # Zero baseline
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current_snapshot_healthy,
            thresholds=thresholds,
        )

        # Should still check p95
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_with_missing_baseline_metrics(
        self,
        validator: IstioLatencyValidator,
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
        validator: IstioLatencyValidator,
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
    async def test_validate_latency_exactly_at_threshold(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation behavior when latency increase is exactly at threshold."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 110.0,  # Exactly 10% increase
                "istio.request.latency.p99": 220.0,  # Exactly 10% increase
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
    async def test_validate_latency_just_over_threshold(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation behavior when latency increase just exceeds threshold."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 110.1,  # Just over 10% increase
                "istio.request.latency.p99": 200.0,
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Just over threshold should fail
        assert result.passed is False
        assert len(result.violations) == 1

    @pytest.mark.asyncio
    async def test_validate_latency_decreased(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation passes when latency actually decreases."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 90.0,  # Decreased by 10%
                "istio.request.latency.p99": 180.0,  # Decreased by 10%
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current,
            thresholds=thresholds,
        )

        # Decreased latency is good
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_with_strict_thresholds(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_healthy: MetricsSnapshot,
        strict_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation with strict thresholds (5% instead of 10%)."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_healthy,  # 5% increase
            thresholds=strict_thresholds,
        )

        # 5% increase should be at threshold and pass
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_validate_includes_metrics_in_result(
        self,
        validator: IstioLatencyValidator,
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
        validator: IstioLatencyValidator,
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
    async def test_validate_violation_messages_include_values(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        current_snapshot_both_degraded: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test that violation messages include actual values and thresholds."""
        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline_snapshot,
            current=current_snapshot_both_degraded,
            thresholds=thresholds,
        )

        assert result.passed is False
        # Check that violations include percentage, baseline, and current values
        for violation in result.violations:
            # Should contain percentage increase
            assert "%" in violation
            # Should contain "ms" unit
            assert "ms" in violation.lower()
            # Should contain "->" showing before/after
            assert "->" in violation

    @pytest.mark.asyncio
    async def test_validate_large_latency_increase(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        baseline_snapshot: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation with very large latency increase."""
        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 500.0,  # 400% increase
                "istio.request.latency.p99": 1000.0,  # 400% increase
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
        assert len(result.violations) == 2

    @pytest.mark.asyncio
    async def test_validate_small_absolute_values(
        self,
        validator: IstioLatencyValidator,
        sample_cluster_config: ClusterConfig,
        thresholds: ValidationThresholds,
    ) -> None:
        """Test validation with very small absolute latency values."""
        baseline = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 1.0,  # 1ms
                "istio.request.latency.p99": 2.0,  # 2ms
            },
            tags={},
        )

        current = MetricsSnapshot(
            timestamp=datetime.utcnow(),
            metrics={
                "istio.request.latency.p95": 1.15,  # 15% increase
                "istio.request.latency.p99": 2.15,  # 7.5% increase
            },
            tags={},
        )

        result = await validator.validate(
            cluster=sample_cluster_config,
            baseline=baseline,
            current=current,
            thresholds=thresholds,
        )

        # Should still detect percentage increase even with small absolute values
        assert result.passed is False
        assert len(result.violations) == 1  # Only p95 exceeds 10%
