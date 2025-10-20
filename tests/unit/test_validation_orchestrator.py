"""Unit tests for ValidationOrchestrator.

Tests the validation orchestrator for coordinating post-upgrade validation.
All external dependencies are mocked to ensure tests are isolated and fast.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.metrics_provider import MetricsProvider
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.validation.validation_orchestrator import ValidationOrchestrator
from guard.validation.validator_registry import ValidatorRegistry


@pytest.fixture
def mock_metrics_provider() -> MagicMock:
    """Create a mock metrics provider."""
    provider = MagicMock(spec=MetricsProvider)
    provider.query_scalar = AsyncMock()
    return provider


@pytest.fixture
def registry() -> ValidatorRegistry:
    """Create a validator registry."""
    return ValidatorRegistry()


@pytest.fixture
def orchestrator(
    registry: ValidatorRegistry, mock_metrics_provider: MagicMock
) -> ValidationOrchestrator:
    """Create a validation orchestrator."""
    return ValidationOrchestrator(
        registry=registry, metrics_provider=mock_metrics_provider, fail_fast=False
    )


@pytest.fixture
def fail_fast_orchestrator(
    registry: ValidatorRegistry, mock_metrics_provider: MagicMock
) -> ValidationOrchestrator:
    """Create a validation orchestrator with fail-fast enabled."""
    return ValidationOrchestrator(
        registry=registry, metrics_provider=mock_metrics_provider, fail_fast=True
    )


@pytest.fixture
def mock_validator() -> MagicMock:
    """Create a mock validator."""
    validator = MagicMock(spec=Validator)
    validator.name = "test_validator"
    validator.is_critical = True
    validator.timeout_seconds = 60
    validator.get_required_metrics = AsyncMock(
        return_value=["istio.request.latency.p95", "istio.request.error.5xx.rate"]
    )
    validator.validate = AsyncMock()
    return validator


@pytest.fixture
def sample_baseline_snapshot() -> MetricsSnapshot:
    """Create a sample baseline metrics snapshot."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 100.0,
            "istio.request.latency.p99": 150.0,
            "istio.request.error.5xx.rate": 0.001,
            "istio.request.total.rate": 1000.0,
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def sample_current_snapshot() -> MetricsSnapshot:
    """Create a sample current metrics snapshot."""
    return MetricsSnapshot(
        timestamp=datetime.utcnow(),
        metrics={
            "istio.request.latency.p95": 105.0,
            "istio.request.latency.p99": 160.0,
            "istio.request.error.5xx.rate": 0.0012,
            "istio.request.total.rate": 1050.0,
        },
        tags={"cluster": "test-cluster", "env": "test"},
    )


@pytest.fixture
def sample_thresholds() -> ValidationThresholds:
    """Create sample validation thresholds."""
    return ValidationThresholds(
        latency_p95_increase_percent=10.0,
        latency_p99_increase_percent=15.0,
        error_rate_max=0.01,
    )


class TestValidationOrchestratorInit:
    """Tests for ValidationOrchestrator initialization."""

    def test_init_success(
        self, registry: ValidatorRegistry, mock_metrics_provider: MagicMock
    ) -> None:
        """Test successful orchestrator initialization."""
        orchestrator = ValidationOrchestrator(
            registry=registry, metrics_provider=mock_metrics_provider, fail_fast=False
        )

        assert orchestrator.registry == registry
        assert orchestrator.metrics == mock_metrics_provider
        assert orchestrator.fail_fast is False

    def test_init_with_fail_fast(
        self, registry: ValidatorRegistry, mock_metrics_provider: MagicMock
    ) -> None:
        """Test initialization with fail-fast enabled."""
        orchestrator = ValidationOrchestrator(
            registry=registry, metrics_provider=mock_metrics_provider, fail_fast=True
        )

        assert orchestrator.fail_fast is True


class TestValidationOrchestratorCaptureBaseline:
    """Tests for baseline metric capture."""

    @pytest.mark.asyncio
    async def test_capture_baseline_success(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test successful baseline metric capture."""
        registry.register(mock_validator)

        # Mock metric query responses
        mock_metrics_provider.query_scalar.side_effect = [100.0, 0.001]

        snapshot = await orchestrator.capture_baseline(
            cluster=sample_cluster_config, duration_minutes=10
        )

        # Verify calls were made
        assert mock_metrics_provider.query_scalar.call_count == 2
        assert snapshot.metrics["istio.request.latency.p95"] == 100.0
        assert snapshot.metrics["istio.request.error.5xx.rate"] == 0.001
        assert snapshot.tags == sample_cluster_config.datadog_tags.model_dump()

    @pytest.mark.asyncio
    async def test_capture_baseline_with_failed_metric(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test baseline capture handles failed metric queries gracefully."""
        registry.register(mock_validator)

        # First metric succeeds, second fails
        mock_metrics_provider.query_scalar.side_effect = [100.0, Exception("Query failed")]

        snapshot = await orchestrator.capture_baseline(
            cluster=sample_cluster_config, duration_minutes=10
        )

        # Verify failed metric is set to None
        assert snapshot.metrics["istio.request.latency.p95"] == 100.0
        assert snapshot.metrics["istio.request.error.5xx.rate"] is None

    @pytest.mark.asyncio
    async def test_capture_baseline_deduplicates_metrics(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test that duplicate metric names are deduplicated."""
        # Create two validators that require the same metrics
        validator1 = MagicMock(spec=Validator)
        validator1.get_required_metrics = AsyncMock(
            return_value=["istio.request.latency.p95", "istio.request.error.5xx.rate"]
        )

        validator2 = MagicMock(spec=Validator)
        validator2.get_required_metrics = AsyncMock(
            return_value=["istio.request.latency.p95", "istio.request.total.rate"]
        )

        registry.register(validator1)
        registry.register(validator2)

        mock_metrics_provider.query_scalar.side_effect = [100.0, 0.001, 1000.0]

        snapshot = await orchestrator.capture_baseline(
            cluster=sample_cluster_config, duration_minutes=10
        )

        # Should query each unique metric only once
        assert mock_metrics_provider.query_scalar.call_count == 3

    @pytest.mark.asyncio
    async def test_capture_baseline_uses_correct_time_range(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test that baseline capture uses correct time range."""
        registry.register(mock_validator)
        mock_metrics_provider.query_scalar.return_value = 100.0

        await orchestrator.capture_baseline(cluster=sample_cluster_config, duration_minutes=10)

        # Check that start_time and end_time are correctly set
        call_args = mock_metrics_provider.query_scalar.call_args_list[0][1]
        start_time = call_args["start_time"]
        end_time = call_args["end_time"]

        time_diff = (end_time - start_time).total_seconds()
        assert 595 <= time_diff <= 605  # Allow 5 second tolerance


class TestValidationOrchestratorCaptureCurrent:
    """Tests for current metric capture."""

    @pytest.mark.asyncio
    async def test_capture_current_success(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
    ) -> None:
        """Test successful current metric capture."""
        # Mock metric query responses
        mock_metrics_provider.query_scalar.side_effect = [105.0, 160.0, 0.0012, 1050.0]

        snapshot = await orchestrator.capture_current(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            duration_minutes=10,
        )

        # Verify calls were made for all baseline metrics
        assert mock_metrics_provider.query_scalar.call_count == 4
        assert snapshot.metrics["istio.request.latency.p95"] == 105.0
        assert snapshot.metrics["istio.request.error.5xx.rate"] == 0.0012

    @pytest.mark.asyncio
    async def test_capture_current_with_failed_metric(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
    ) -> None:
        """Test current capture handles failed metric queries gracefully."""
        # Some metrics succeed, some fail
        mock_metrics_provider.query_scalar.side_effect = [
            105.0,
            Exception("Query failed"),
            0.0012,
            Exception("Network timeout"),
        ]

        snapshot = await orchestrator.capture_current(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            duration_minutes=10,
        )

        # Verify failed metrics are set to None
        assert snapshot.metrics["istio.request.latency.p95"] == 105.0
        assert snapshot.metrics["istio.request.latency.p99"] is None
        assert snapshot.metrics["istio.request.error.5xx.rate"] == 0.0012
        assert snapshot.metrics["istio.request.total.rate"] is None

    @pytest.mark.asyncio
    async def test_capture_current_queries_same_metrics_as_baseline(
        self,
        orchestrator: ValidationOrchestrator,
        mock_metrics_provider: MagicMock,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
    ) -> None:
        """Test that current capture queries the same metrics as baseline."""
        mock_metrics_provider.query_scalar.return_value = 100.0

        await orchestrator.capture_current(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            duration_minutes=10,
        )

        # Should query each metric from baseline
        assert mock_metrics_provider.query_scalar.call_count == len(
            sample_baseline_snapshot.metrics
        )

        # Verify metric names match
        called_metrics = [
            call[1]["metric_name"] for call in mock_metrics_provider.query_scalar.call_args_list
        ]
        assert set(called_metrics) == set(sample_baseline_snapshot.metrics.keys())


class TestValidationOrchestratorValidateUpgrade:
    """Tests for upgrade validation."""

    @pytest.mark.asyncio
    async def test_validate_upgrade_all_pass(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation when all validators pass."""
        registry.register(mock_validator)

        # Mock successful validation
        mock_validator.validate.return_value = ValidationResult(
            cluster_id=sample_cluster_config.cluster_id,
            validator_name="test_validator",
            passed=True,
            violations=[],
            metrics={},
            timestamp=datetime.utcnow(),
        )

        results = await orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        assert len(results) == 1
        assert results[0].passed is True
        assert len(results[0].violations) == 0

    @pytest.mark.asyncio
    async def test_validate_upgrade_with_failures(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation when validators fail."""
        registry.register(mock_validator)

        # Mock failed validation
        mock_validator.validate.return_value = ValidationResult(
            cluster_id=sample_cluster_config.cluster_id,
            validator_name="test_validator",
            passed=False,
            violations=["Latency increased beyond threshold"],
            metrics={},
            timestamp=datetime.utcnow(),
        )

        results = await orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert len(results[0].violations) == 1

    @pytest.mark.asyncio
    async def test_validate_upgrade_timeout_handling(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles timeouts properly."""
        registry.register(mock_validator)

        # Mock validator that times out
        async def slow_validate(*args, **kwargs):
            await asyncio.sleep(100)

        mock_validator.validate.side_effect = slow_validate
        mock_validator.timeout_seconds = 1  # Short timeout

        results = await orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert "timed out" in results[0].violations[0].lower()

    @pytest.mark.asyncio
    async def test_validate_upgrade_exception_handling(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation handles exceptions properly."""
        registry.register(mock_validator)

        # Mock validator that raises exception
        mock_validator.validate.side_effect = Exception("Database connection failed")

        results = await orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert "failed" in results[0].violations[0].lower()

    @pytest.mark.asyncio
    async def test_validate_upgrade_multiple_validators(
        self,
        orchestrator: ValidationOrchestrator,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test validation with multiple validators."""
        # Create multiple validators
        validator1 = MagicMock(spec=Validator)
        validator1.name = "validator_1"
        validator1.is_critical = True
        validator1.timeout_seconds = 60
        validator1.validate = AsyncMock(
            return_value=ValidationResult(
                cluster_id=sample_cluster_config.cluster_id,
                validator_name="validator_1",
                passed=True,
                violations=[],
                metrics={},
                timestamp=datetime.utcnow(),
            )
        )

        validator2 = MagicMock(spec=Validator)
        validator2.name = "validator_2"
        validator2.is_critical = False
        validator2.timeout_seconds = 30
        validator2.validate = AsyncMock(
            return_value=ValidationResult(
                cluster_id=sample_cluster_config.cluster_id,
                validator_name="validator_2",
                passed=False,
                violations=["Minor issue detected"],
                metrics={},
                timestamp=datetime.utcnow(),
            )
        )

        registry.register(validator1)
        registry.register(validator2)

        results = await orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    @pytest.mark.asyncio
    async def test_validate_upgrade_fail_fast_stops_on_critical_failure(
        self,
        fail_fast_orchestrator: ValidationOrchestrator,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test that fail-fast stops on critical validator failure."""
        # Create two critical validators
        validator1 = MagicMock(spec=Validator)
        validator1.name = "validator_1"
        validator1.is_critical = True
        validator1.timeout_seconds = 60
        validator1.validate = AsyncMock(
            return_value=ValidationResult(
                cluster_id=sample_cluster_config.cluster_id,
                validator_name="validator_1",
                passed=False,
                violations=["Critical failure"],
                metrics={},
                timestamp=datetime.utcnow(),
            )
        )

        validator2 = MagicMock(spec=Validator)
        validator2.name = "validator_2"
        validator2.is_critical = True
        validator2.timeout_seconds = 60
        validator2.validate = AsyncMock()

        registry.register(validator1)
        registry.register(validator2)

        results = await fail_fast_orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        # Should only have one result (stopped after first failure)
        assert len(results) == 1
        assert results[0].passed is False
        # Validator2 should never be called
        validator2.validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_upgrade_fail_fast_continues_on_non_critical_failure(
        self,
        fail_fast_orchestrator: ValidationOrchestrator,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test that fail-fast continues on non-critical validator failure."""
        # Non-critical validator fails, then critical validator
        validator1 = MagicMock(spec=Validator)
        validator1.name = "validator_1"
        validator1.is_critical = False
        validator1.timeout_seconds = 60
        validator1.validate = AsyncMock(
            return_value=ValidationResult(
                cluster_id=sample_cluster_config.cluster_id,
                validator_name="validator_1",
                passed=False,
                violations=["Non-critical failure"],
                metrics={},
                timestamp=datetime.utcnow(),
            )
        )

        validator2 = MagicMock(spec=Validator)
        validator2.name = "validator_2"
        validator2.is_critical = True
        validator2.timeout_seconds = 60
        validator2.validate = AsyncMock(
            return_value=ValidationResult(
                cluster_id=sample_cluster_config.cluster_id,
                validator_name="validator_2",
                passed=True,
                violations=[],
                metrics={},
                timestamp=datetime.utcnow(),
            )
        )

        registry.register(validator1)
        registry.register(validator2)

        results = await fail_fast_orchestrator.validate_upgrade(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
        )

        # Should have both results (continued after non-critical failure)
        assert len(results) == 2
        validator2.validate.assert_called_once()


class TestValidationOrchestratorRunSpecificValidators:
    """Tests for running specific validators."""

    @pytest.mark.asyncio
    async def test_run_specific_validators_success(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test running specific validators by name."""
        mock_validator.name = "test_validator"
        registry.register(mock_validator)

        mock_validator.validate.return_value = ValidationResult(
            cluster_id=sample_cluster_config.cluster_id,
            validator_name="test_validator",
            passed=True,
            violations=[],
            metrics={},
            timestamp=datetime.utcnow(),
        )

        results = await orchestrator.run_specific_validators(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
            validator_names=["test_validator"],
        )

        assert len(results) == 1
        assert results[0].validator_name == "test_validator"

    @pytest.mark.asyncio
    async def test_run_specific_validators_not_found(
        self,
        orchestrator: ValidationOrchestrator,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test running non-existent validators logs warning and skips."""
        results = await orchestrator.run_specific_validators(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
            validator_names=["non_existent_validator"],
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_run_specific_validators_exception_handling(
        self,
        orchestrator: ValidationOrchestrator,
        mock_validator: MagicMock,
        registry: ValidatorRegistry,
        sample_cluster_config: ClusterConfig,
        sample_baseline_snapshot: MetricsSnapshot,
        sample_current_snapshot: MetricsSnapshot,
        sample_thresholds: ValidationThresholds,
    ) -> None:
        """Test that exceptions in specific validators are handled gracefully."""
        mock_validator.name = "test_validator"
        registry.register(mock_validator)

        # Mock validator that raises exception
        mock_validator.validate.side_effect = Exception("Validation error")

        results = await orchestrator.run_specific_validators(
            cluster=sample_cluster_config,
            baseline=sample_baseline_snapshot,
            current=sample_current_snapshot,
            thresholds=sample_thresholds,
            validator_names=["test_validator"],
        )

        # Exception should be caught and logged, no result returned
        assert len(results) == 0
