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

        assert thresholds.latency_increase_percent == 10.0
        assert thresholds.error_rate_max == 0.001
        assert thresholds.resource_increase_percent == 50.0

    def test_validation_thresholds_custom_values(self) -> None:
        """Test ValidationThresholds with custom values."""
        thresholds = ValidationThresholds(
            latency_increase_percent=5.0, error_rate_max=0.0005, resource_increase_percent=25.0
        )

        assert thresholds.latency_increase_percent == 5.0
        assert thresholds.error_rate_max == 0.0005
        assert thresholds.resource_increase_percent == 25.0
