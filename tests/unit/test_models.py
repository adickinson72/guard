"""Unit tests for core data models.

This demonstrates TDD approach:
1. Write tests first (define expected behavior)
2. Implement minimal code to pass tests
3. Refactor while keeping tests passing
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from guard.core.models import (
    CheckResult,
    ClusterConfig,
    ClusterMetadata,
    ClusterStatus,
    DatadogTags,
    UpgradeHistoryEntry,
    ValidationThresholds,
    get_metric_aggregation,
)


class TestClusterStatus:
    """Tests for ClusterStatus enum."""

    def test_cluster_status_values(self) -> None:
        """Test that ClusterStatus enum has expected values."""
        assert ClusterStatus.PENDING.value == "pending"
        assert ClusterStatus.PRE_CHECK_RUNNING.value == "pre-check-running"
        assert ClusterStatus.HEALTHY.value == "healthy"
        assert ClusterStatus.ROLLBACK_REQUIRED.value == "rollback-required"

    def test_cluster_status_membership(self) -> None:
        """Test that we can check status membership."""
        assert ClusterStatus.PENDING in ClusterStatus
        assert "invalid-status" not in ClusterStatus.__members__


class TestClusterConfig:
    """Tests for ClusterConfig model."""

    def test_cluster_config_creation_with_required_fields(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test creating a ClusterConfig with required fields."""
        assert sample_cluster_config.cluster_id == "eks-test-us-east-1"
        assert sample_cluster_config.batch_id == "test"
        assert sample_cluster_config.environment == "test"
        assert sample_cluster_config.status == ClusterStatus.PENDING

    def test_cluster_config_missing_required_field_raises_error(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ClusterConfig(
                cluster_id="test-cluster",
                # Missing required fields
            )
        assert "batch_id" in str(exc_info.value)

    def test_cluster_config_defaults(self, sample_cluster_config: ClusterConfig) -> None:
        """Test that ClusterConfig has correct default values."""
        assert sample_cluster_config.status == ClusterStatus.PENDING
        assert isinstance(sample_cluster_config.last_updated, datetime)
        assert sample_cluster_config.upgrade_history == []
        assert isinstance(sample_cluster_config.metadata, ClusterMetadata)

    def test_cluster_config_datadog_tags_structure(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that Datadog tags are properly structured."""
        tags = sample_cluster_config.datadog_tags
        assert tags.cluster == "eks-test-us-east-1"
        assert tags.service == "istio-system"
        assert tags.env == "test"

    def test_cluster_config_update_status(self, sample_cluster_config: ClusterConfig) -> None:
        """Test updating cluster status."""
        original_time = sample_cluster_config.last_updated
        sample_cluster_config.status = ClusterStatus.PRE_CHECK_PASSED
        sample_cluster_config.last_updated = datetime.utcnow()

        assert sample_cluster_config.status == ClusterStatus.PRE_CHECK_PASSED
        assert sample_cluster_config.last_updated > original_time

    def test_cluster_config_add_upgrade_history(self, sample_cluster_config: ClusterConfig) -> None:
        """Test adding upgrade history entry."""
        history_entry = UpgradeHistoryEntry(
            version="1.19.3", date=datetime.utcnow(), status="success"
        )
        sample_cluster_config.upgrade_history.append(history_entry)

        assert len(sample_cluster_config.upgrade_history) == 1
        assert sample_cluster_config.upgrade_history[0].version == "1.19.3"

    def test_cluster_config_serialization(self, sample_cluster_config: ClusterConfig) -> None:
        """Test that ClusterConfig can be serialized to dict."""
        config_dict = sample_cluster_config.model_dump()

        assert isinstance(config_dict, dict)
        assert config_dict["cluster_id"] == "eks-test-us-east-1"
        assert config_dict["status"] == "pending"  # Enum should be converted to value

    def test_cluster_config_deserialization(self) -> None:
        """Test that ClusterConfig can be created from dict."""
        config_dict = {
            "cluster_id": "test-cluster",
            "batch_id": "test-batch",
            "environment": "test",
            "region": "us-east-1",
            "gitlab_repo": "infra/test",
            "flux_config_path": "test/path",
            "aws_role_arn": "arn:aws:iam::123:role/test",
            "current_istio_version": "1.19.0",
            "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
            "owner_team": "team",
            "owner_handle": "@team",
        }

        config = ClusterConfig(**config_dict)
        assert config.cluster_id == "test-cluster"
        assert config.status == ClusterStatus.PENDING


class TestCheckResult:
    """Tests for CheckResult model."""

    def test_check_result_passed(self) -> None:
        """Test creating a passed check result."""
        result = CheckResult(
            check_name="kubernetes_health",
            passed=True,
            message="All nodes are ready",
            metrics={"ready_nodes": 3, "total_nodes": 3},
        )

        assert result.passed is True
        assert result.check_name == "kubernetes_health"
        assert result.metrics["ready_nodes"] == 3

    def test_check_result_failed(self) -> None:
        """Test creating a failed check result."""
        result = CheckResult(
            check_name="datadog_alerts",
            passed=False,
            message="2 active alerts found",
            metrics={"alert_count": 2},
        )

        assert result.passed is False
        assert "active alerts" in result.message
        assert isinstance(result.timestamp, datetime)

    def test_check_result_defaults(self) -> None:
        """Test CheckResult default values."""
        result = CheckResult(check_name="test", passed=True, message="Test passed")

        assert result.metrics == {}
        assert isinstance(result.timestamp, datetime)


class TestValidationThresholds:
    """Tests for ValidationThresholds model."""

    def test_validation_thresholds_defaults(self) -> None:
        """Test ValidationThresholds default values."""
        thresholds = ValidationThresholds()

        assert thresholds.latency_p95_increase_percent == 10.0
        assert thresholds.latency_p99_increase_percent == 15.0
        assert thresholds.error_rate_max == 0.001
        assert thresholds.resource_increase_percent == 25.0

    def test_validation_thresholds_custom_values(self) -> None:
        """Test ValidationThresholds with custom values."""
        thresholds = ValidationThresholds(
            latency_p95_increase_percent=5.0,
            latency_p99_increase_percent=8.0,
            error_rate_max=0.0005,
            resource_increase_percent=20.0,
        )

        assert thresholds.latency_p95_increase_percent == 5.0
        assert thresholds.latency_p99_increase_percent == 8.0
        assert thresholds.error_rate_max == 0.0005
        assert thresholds.resource_increase_percent == 20.0

    def test_get_for_environment_without_overrides(self) -> None:
        """Test get_for_environment returns base thresholds when no override exists."""
        thresholds = ValidationThresholds(
            latency_p95_increase_percent=10.0,
            error_rate_max=0.001,
        )

        result = thresholds.get_for_environment("production")

        assert result.latency_p95_increase_percent == 10.0
        assert result.error_rate_max == 0.001
        assert result is thresholds  # Should return self when no override

    def test_get_for_environment_with_overrides(self) -> None:
        """Test get_for_environment applies environment-specific overrides."""
        prod_override = ValidationThresholds(
            latency_p95_increase_percent=5.0,
            error_rate_max=0.0005,
        )

        thresholds = ValidationThresholds(
            latency_p95_increase_percent=10.0,
            latency_p99_increase_percent=15.0,
            error_rate_max=0.001,
            resource_increase_percent=25.0,
            environment_overrides={"production": prod_override},
        )

        result = thresholds.get_for_environment("production")

        # Overridden values
        assert result.latency_p95_increase_percent == 5.0
        assert result.error_rate_max == 0.0005

        # Non-overridden values should remain from base
        assert result.latency_p99_increase_percent == 15.0
        assert result.resource_increase_percent == 25.0

    def test_get_for_environment_partial_override(self) -> None:
        """Test get_for_environment with partial overrides merges correctly."""
        dev_override = ValidationThresholds(
            latency_p95_increase_percent=20.0,  # More lenient for dev
        )

        thresholds = ValidationThresholds(
            latency_p95_increase_percent=10.0,
            latency_p99_increase_percent=15.0,
            error_rate_max=0.001,
            environment_overrides={"dev": dev_override},
        )

        result = thresholds.get_for_environment("dev")

        # Override applied
        assert result.latency_p95_increase_percent == 20.0

        # Base values preserved
        assert result.latency_p99_increase_percent == 15.0
        assert result.error_rate_max == 0.001


class TestGetMetricAggregation:
    """Tests for get_metric_aggregation function."""

    def test_get_metric_aggregation_known_metric(self) -> None:
        """Test get_metric_aggregation returns correct aggregation for known metrics."""
        assert get_metric_aggregation("istio.request.duration.p95") == "p95"
        assert get_metric_aggregation("istio.request.duration.p99") == "p99"
        assert get_metric_aggregation("istio.request.error_rate") == "max"
        assert get_metric_aggregation("istio.request.count") == "sum"
        assert get_metric_aggregation("istiod.cpu") == "avg"
        assert get_metric_aggregation("istiod.memory") == "avg"
        assert get_metric_aggregation("pilot_total_xds_rejects") == "sum"

    def test_get_metric_aggregation_unknown_metric_defaults_to_avg(self) -> None:
        """Test get_metric_aggregation returns 'avg' for unknown metrics."""
        assert get_metric_aggregation("unknown.metric.name") == "avg"
        assert get_metric_aggregation("custom.metric") == "avg"
        assert get_metric_aggregation("") == "avg"

    def test_get_metric_aggregation_all_aggregation_types(self) -> None:
        """Test that all aggregation types are covered."""
        # P95
        assert get_metric_aggregation("latency.p95") == "p95"

        # P99
        assert get_metric_aggregation("latency.p99") == "p99"

        # MAX
        assert get_metric_aggregation("error_rate") == "max"

        # SUM
        assert get_metric_aggregation("request.count") == "sum"

        # AVG (explicit)
        assert get_metric_aggregation("cpu.usage") == "avg"

        # AVG (default)
        assert get_metric_aggregation("unconfigured.metric") == "avg"
