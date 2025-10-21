"""Unit tests for metrics collection and aggregation.

This module tests the metrics collection system including:
- Metric recording and storage
- Success rate calculations
- Duration aggregations
- Error breakdowns
- Operation counting
- Summary generation
- Context manager timing
"""

from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from guard.utils.metrics import (
    MetricsCollector,
    OperationMetric,
    OperationStatus,
    OperationType,
    get_metrics_collector,
    timed_operation,
)


class TestOperationMetric:
    """Test OperationMetric dataclass."""

    def test_operation_metric_creation(self):
        """Test creating an operation metric with all fields."""
        metric = OperationMetric(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.5,
            cluster_id="test-cluster",
            batch_id="test-batch",
            error_type=None,
            error_message=None,
            metadata={"check_type": "health"},
        )

        assert metric.operation_type == OperationType.PRE_CHECK
        assert metric.status == OperationStatus.SUCCESS
        assert metric.duration_seconds == 1.5
        assert metric.cluster_id == "test-cluster"
        assert metric.batch_id == "test-batch"
        assert metric.error_type is None
        assert metric.error_message is None
        assert metric.metadata == {"check_type": "health"}
        assert isinstance(metric.timestamp, datetime)

    def test_operation_metric_with_error(self):
        """Test creating an operation metric with error information."""
        metric = OperationMetric(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.ERROR,
            duration_seconds=0.5,
            cluster_id="test-cluster",
            error_type="ValidationError",
            error_message="Check failed",
        )

        assert metric.status == OperationStatus.ERROR
        assert metric.error_type == "ValidationError"
        assert metric.error_message == "Check failed"

    def test_operation_metric_defaults(self):
        """Test operation metric uses default values for optional fields."""
        metric = OperationMetric(
            operation_type=OperationType.MR_CREATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
        )

        assert metric.cluster_id is None
        assert metric.batch_id is None
        assert metric.error_type is None
        assert metric.error_message is None
        assert metric.metadata == {}


class TestMetricsCollector:
    """Test MetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create a fresh metrics collector for each test."""
        return MetricsCollector()

    def test_metrics_collector_initialization(self, collector):
        """Test metrics collector initializes with empty metrics list."""
        assert collector.metrics == []

    def test_record_operation_basic(self, collector):
        """Test recording a basic operation."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.5,
        )

        assert len(collector.metrics) == 1
        metric = collector.metrics[0]
        assert metric.operation_type == OperationType.PRE_CHECK
        assert metric.status == OperationStatus.SUCCESS
        assert metric.duration_seconds == 1.5

    def test_record_operation_with_context(self, collector):
        """Test recording operation with cluster and batch context."""
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.5,
            cluster_id="cluster-1",
            batch_id="test-batch",
        )

        metric = collector.metrics[0]
        assert metric.cluster_id == "cluster-1"
        assert metric.batch_id == "test-batch"

    def test_record_operation_with_error(self, collector):
        """Test recording operation with error information."""
        collector.record_operation(
            operation_type=OperationType.POST_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=0.5,
            error_type="CheckFailed",
            error_message="Pod not ready",
        )

        metric = collector.metrics[0]
        assert metric.status == OperationStatus.FAILURE
        assert metric.error_type == "CheckFailed"
        assert metric.error_message == "Pod not ready"

    def test_record_operation_with_metadata(self, collector):
        """Test recording operation with custom metadata."""
        collector.record_operation(
            operation_type=OperationType.ROLLBACK,
            status=OperationStatus.SUCCESS,
            duration_seconds=3.0,
            check_type="sidecar_version",
            attempts=2,
        )

        metric = collector.metrics[0]
        assert metric.metadata == {"check_type": "sidecar_version", "attempts": 2}

    @patch("guard.utils.metrics.logger")
    def test_record_operation_logs_metric(self, mock_logger, collector):
        """Test that recording operation logs the metric."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
            cluster_id="test-cluster",
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "operation_metric"
        assert call_args[1]["operation_type"] == "pre_check"
        assert call_args[1]["status"] == "success"
        assert call_args[1]["duration_seconds"] == 1.0
        assert call_args[1]["cluster_id"] == "test-cluster"

    def test_get_success_rate_all_success(self, collector):
        """Test success rate calculation with all successful operations."""
        for _i in range(10):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )

        success_rate = collector.get_success_rate()
        assert success_rate == 100.0

    def test_get_success_rate_mixed(self, collector):
        """Test success rate calculation with mixed results."""
        # 7 success, 3 failures
        for _i in range(7):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )
        for _i in range(3):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=1.0,
            )

        success_rate = collector.get_success_rate()
        assert success_rate == 70.0

    def test_get_success_rate_no_metrics(self, collector):
        """Test success rate returns 0 when no metrics."""
        success_rate = collector.get_success_rate()
        assert success_rate == 0.0

    def test_get_success_rate_filtered_by_operation_type(self, collector):
        """Test success rate filtered by operation type."""
        # Pre-check: 5 success, 5 failures
        for _i in range(5):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )
        for _i in range(5):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=1.0,
            )

        # Post-check: all success
        for _i in range(10):
            collector.record_operation(
                operation_type=OperationType.POST_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )

        pre_check_rate = collector.get_success_rate(operation_type=OperationType.PRE_CHECK)
        post_check_rate = collector.get_success_rate(operation_type=OperationType.POST_CHECK)

        assert pre_check_rate == 50.0
        assert post_check_rate == 100.0

    def test_get_success_rate_filtered_by_batch(self, collector):
        """Test success rate filtered by batch ID."""
        # Batch A: 80% success
        for _i in range(8):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
                batch_id="batch-a",
            )
        for _i in range(2):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=1.0,
                batch_id="batch-a",
            )

        # Batch B: 60% success
        for _i in range(6):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
                batch_id="batch-b",
            )
        for _i in range(4):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=1.0,
                batch_id="batch-b",
            )

        batch_a_rate = collector.get_success_rate(batch_id="batch-a")
        batch_b_rate = collector.get_success_rate(batch_id="batch-b")

        assert batch_a_rate == 80.0
        assert batch_b_rate == 60.0

    def test_get_average_duration_basic(self, collector):
        """Test average duration calculation."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=3.0,
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
        )

        avg_duration = collector.get_average_duration()
        assert avg_duration == 2.0

    def test_get_average_duration_no_metrics(self, collector):
        """Test average duration returns 0 when no metrics."""
        avg_duration = collector.get_average_duration()
        assert avg_duration == 0.0

    def test_get_average_duration_filtered(self, collector):
        """Test average duration with filters."""
        # Pre-check operations: avg 1.0s
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
        )

        # Validation operations: avg 5.0s
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=5.0,
        )
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=5.0,
        )

        pre_check_avg = collector.get_average_duration(operation_type=OperationType.PRE_CHECK)
        validation_avg = collector.get_average_duration(operation_type=OperationType.VALIDATION)

        assert pre_check_avg == 1.0
        assert validation_avg == 5.0

    def test_get_error_breakdown_basic(self, collector):
        """Test error breakdown calculation."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            error_type="PodNotReady",
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            error_type="PodNotReady",
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.ERROR,
            duration_seconds=1.0,
            error_type="TimeoutError",
        )

        breakdown = collector.get_error_breakdown()
        assert breakdown == {"PodNotReady": 2, "TimeoutError": 1}

    def test_get_error_breakdown_excludes_success(self, collector):
        """Test error breakdown excludes successful operations."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            error_type="CheckFailed",
        )

        breakdown = collector.get_error_breakdown()
        assert breakdown == {"CheckFailed": 1}

    def test_get_error_breakdown_no_error_type(self, collector):
        """Test error breakdown ignores errors without type."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            error_type=None,  # No error type
        )

        breakdown = collector.get_error_breakdown()
        assert breakdown == {}

    def test_get_error_breakdown_filtered(self, collector):
        """Test error breakdown with filters."""
        # Batch A errors
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            batch_id="batch-a",
            error_type="ErrorA",
        )

        # Batch B errors
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            batch_id="batch-b",
            error_type="ErrorB",
        )

        batch_a_errors = collector.get_error_breakdown(batch_id="batch-a")
        batch_b_errors = collector.get_error_breakdown(batch_id="batch-b")

        assert batch_a_errors == {"ErrorA": 1}
        assert batch_b_errors == {"ErrorB": 1}

    def test_get_operation_counts_basic(self, collector):
        """Test operation counts by type and status."""
        # 3 successful pre-checks
        for _i in range(3):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )

        # 2 failed pre-checks
        for _i in range(2):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=1.0,
            )

        # 1 successful validation
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
        )

        counts = collector.get_operation_counts()
        assert counts == {
            "pre_check": {"success": 3, "failure": 2},
            "validation": {"success": 1},
        }

    def test_get_operation_counts_empty(self, collector):
        """Test operation counts with no metrics."""
        counts = collector.get_operation_counts()
        assert counts == {}

    def test_get_operation_counts_filtered_by_batch(self, collector):
        """Test operation counts filtered by batch."""
        # Batch A
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
            batch_id="batch-a",
        )

        # Batch B
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.FAILURE,
            duration_seconds=1.0,
            batch_id="batch-b",
        )

        batch_a_counts = collector.get_operation_counts(batch_id="batch-a")
        batch_b_counts = collector.get_operation_counts(batch_id="batch-b")

        assert batch_a_counts == {"pre_check": {"success": 1}}
        assert batch_b_counts == {"pre_check": {"failure": 1}}

    def test_get_summary_comprehensive(self, collector):
        """Test comprehensive summary generation."""
        # 7 successful operations
        for _i in range(7):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
            )

        # 3 failed operations with errors
        for _i in range(3):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.FAILURE,
                duration_seconds=2.0,
                error_type="CheckFailed",
            )

        summary = collector.get_summary()

        assert summary["total_operations"] == 10
        assert summary["success_rate"] == 70.0
        assert summary["average_duration"] == 1.3  # (7*1.0 + 3*2.0) / 10
        assert summary["operation_counts"] == {"pre_check": {"success": 7, "failure": 3}}
        assert summary["error_breakdown"] == {"CheckFailed": 3}

    def test_get_summary_empty(self, collector):
        """Test summary with no metrics."""
        summary = collector.get_summary()

        assert summary == {
            "total_operations": 0,
            "success_rate": 0.0,
            "average_duration": 0.0,
            "operation_counts": {},
            "error_breakdown": {},
        }

    def test_get_summary_filtered_by_batch(self, collector):
        """Test summary filtered by batch."""
        # Batch A: 2 operations
        for _i in range(2):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=1.0,
                batch_id="batch-a",
            )

        # Batch B: 3 operations
        for _i in range(3):
            collector.record_operation(
                operation_type=OperationType.PRE_CHECK,
                status=OperationStatus.SUCCESS,
                duration_seconds=2.0,
                batch_id="batch-b",
            )

        batch_a_summary = collector.get_summary(batch_id="batch-a")
        batch_b_summary = collector.get_summary(batch_id="batch-b")

        assert batch_a_summary["total_operations"] == 2
        assert batch_a_summary["average_duration"] == 1.0
        assert batch_b_summary["total_operations"] == 3
        assert batch_b_summary["average_duration"] == 2.0

    def test_filter_metrics_by_operation_type(self, collector):
        """Test filtering metrics by operation type."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
        )
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
        )

        filtered = collector._filter_metrics(operation_type=OperationType.PRE_CHECK)
        assert len(filtered) == 1
        assert filtered[0].operation_type == OperationType.PRE_CHECK

    def test_filter_metrics_by_batch_id(self, collector):
        """Test filtering metrics by batch ID."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
            batch_id="batch-a",
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
            batch_id="batch-b",
        )

        filtered = collector._filter_metrics(batch_id="batch-a")
        assert len(filtered) == 1
        assert filtered[0].batch_id == "batch-a"

    def test_filter_metrics_multiple_criteria(self, collector):
        """Test filtering metrics by multiple criteria."""
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=1.0,
            batch_id="batch-a",
        )
        collector.record_operation(
            operation_type=OperationType.VALIDATION,
            status=OperationStatus.SUCCESS,
            duration_seconds=2.0,
            batch_id="batch-a",
        )
        collector.record_operation(
            operation_type=OperationType.PRE_CHECK,
            status=OperationStatus.SUCCESS,
            duration_seconds=3.0,
            batch_id="batch-b",
        )

        filtered = collector._filter_metrics(
            operation_type=OperationType.PRE_CHECK, batch_id="batch-a"
        )
        assert len(filtered) == 1
        assert filtered[0].operation_type == OperationType.PRE_CHECK
        assert filtered[0].batch_id == "batch-a"


class TestGlobalMetricsCollector:
    """Test global metrics collector singleton."""

    def test_get_metrics_collector_returns_singleton(self):
        """Test get_metrics_collector returns same instance."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_get_metrics_collector_returns_metrics_collector(self):
        """Test get_metrics_collector returns MetricsCollector instance."""
        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)


class TestTimedOperation:
    """Test timed_operation context manager."""

    def test_timed_operation_success(self):
        """Test timing a successful operation."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(OperationType.PRE_CHECK, cluster_id="test-cluster") as timer:
                time.sleep(0.1)
                timer.success()

        assert len(collector.metrics) == 1
        metric = collector.metrics[0]
        assert metric.operation_type == OperationType.PRE_CHECK
        assert metric.status == OperationStatus.SUCCESS
        assert metric.cluster_id == "test-cluster"
        assert metric.duration_seconds >= 0.1

    def test_timed_operation_failure(self):
        """Test timing a failed operation."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(OperationType.VALIDATION) as timer:
                timer.failure(error_type="ValidationError", error_message="Check failed")

        metric = collector.metrics[0]
        assert metric.status == OperationStatus.FAILURE
        assert metric.error_type == "ValidationError"
        assert metric.error_message == "Check failed"

    def test_timed_operation_timeout(self):
        """Test timing an operation that times out."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(OperationType.POST_CHECK) as timer:
                timer.timeout()

        metric = collector.metrics[0]
        assert metric.status == OperationStatus.TIMEOUT

    def test_timed_operation_auto_detect_exception(self):
        """Test timed_operation auto-detects exceptions."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            try:
                with timed_operation(OperationType.PRE_CHECK):
                    raise ValueError("Test error")
            except ValueError:
                pass

        metric = collector.metrics[0]
        assert metric.status == OperationStatus.ERROR
        assert metric.error_type == "ValueError"
        assert metric.error_message == "Test error"

    def test_timed_operation_auto_success_no_exception(self):
        """Test timed_operation auto-marks success when no exception and no explicit status."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(OperationType.MR_CREATION):
                pass  # No explicit success() call

        metric = collector.metrics[0]
        assert metric.status == OperationStatus.SUCCESS

    def test_timed_operation_with_metadata(self):
        """Test timed_operation with custom metadata."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(
                OperationType.ROLLBACK,
                cluster_id="test-cluster",
                batch_id="test-batch",
                version="1.20.0",
            ) as timer:
                timer.success()

        metric = collector.metrics[0]
        assert metric.cluster_id == "test-cluster"
        assert metric.batch_id == "test-batch"
        assert metric.metadata == {"version": "1.20.0"}

    def test_timed_operation_measures_accurate_duration(self):
        """Test timed_operation measures duration accurately."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            with timed_operation(OperationType.VALIDATION) as timer:
                time.sleep(0.2)
                timer.success()

        metric = collector.metrics[0]
        # Allow some variance in timing
        assert 0.19 <= metric.duration_seconds <= 0.3

    def test_timed_operation_explicit_status_overrides_auto_detect(self):
        """Test explicit status setting overrides auto-detection."""
        collector = MetricsCollector()

        with patch("guard.utils.metrics.get_metrics_collector", return_value=collector):
            try:
                with timed_operation(OperationType.PRE_CHECK) as timer:
                    timer.success()  # Explicit success
                    raise ValueError("Test error")
            except ValueError:
                pass

        metric = collector.metrics[0]
        # Explicit success should be recorded, not ERROR from exception
        assert metric.status == OperationStatus.SUCCESS

    def test_timed_operation_initialization_parameters(self):
        """Test timed_operation stores initialization parameters correctly."""
        timer = timed_operation(
            OperationType.BATCH_UPGRADE,
            cluster_id="cluster-1",
            batch_id="prod-wave-1",
            custom_field="value",
        )

        assert timer.operation_type == OperationType.BATCH_UPGRADE
        assert timer.cluster_id == "cluster-1"
        assert timer.batch_id == "prod-wave-1"
        assert timer.metadata == {"custom_field": "value"}
        assert timer.start_time is None
        assert timer.status is None


class TestOperationEnums:
    """Test operation type and status enums."""

    def test_operation_type_values(self):
        """Test OperationType enum values."""
        assert OperationType.PRE_CHECK.value == "pre_check"
        assert OperationType.MR_CREATION.value == "mr_creation"
        assert OperationType.POST_CHECK.value == "post_check"
        assert OperationType.VALIDATION.value == "validation"
        assert OperationType.ROLLBACK.value == "rollback"
        assert OperationType.BATCH_UPGRADE.value == "batch_upgrade"

    def test_operation_status_values(self):
        """Test OperationStatus enum values."""
        assert OperationStatus.SUCCESS.value == "success"
        assert OperationStatus.FAILURE.value == "failure"
        assert OperationStatus.TIMEOUT.value == "timeout"
        assert OperationStatus.ERROR.value == "error"
