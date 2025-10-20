"""Observability metrics for GUARD operations."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from guard.utils.logging import get_logger

logger = get_logger(__name__)


class OperationType(str, Enum):
    """Types of operations to track."""

    PRE_CHECK = "pre_check"
    MR_CREATION = "mr_creation"
    POST_CHECK = "post_check"
    VALIDATION = "validation"
    ROLLBACK = "rollback"
    BATCH_UPGRADE = "batch_upgrade"


class OperationStatus(str, Enum):
    """Status of operations."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class OperationMetric:
    """Metrics for a single operation."""

    operation_type: OperationType
    status: OperationStatus
    duration_seconds: float
    cluster_id: str | None = None
    batch_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MetricsCollector:
    """Collects and aggregates metrics for GUARD operations.

    This class provides a simple interface for tracking operation metrics
    including success rates, durations, and error types. It stores metrics
    in memory for the current session and logs them for external collection
    by observability platforms.
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.metrics: list[OperationMetric] = []
        logger.debug("metrics_collector_initialized")

    def record_operation(
        self,
        operation_type: OperationType,
        status: OperationStatus,
        duration_seconds: float,
        cluster_id: str | None = None,
        batch_id: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record a completed operation.

        Args:
            operation_type: Type of operation
            status: Operation status
            duration_seconds: Duration in seconds
            cluster_id: Optional cluster ID
            batch_id: Optional batch ID
            error_type: Optional error type
            error_message: Optional error message
            **metadata: Additional metadata
        """
        metric = OperationMetric(
            operation_type=operation_type,
            status=status,
            duration_seconds=duration_seconds,
            cluster_id=cluster_id,
            batch_id=batch_id,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata,
        )

        self.metrics.append(metric)

        # Log metric for external collection
        logger.info(
            "operation_metric",
            operation_type=operation_type.value,
            status=status.value,
            duration_seconds=duration_seconds,
            cluster_id=cluster_id,
            batch_id=batch_id,
            error_type=error_type,
            **metadata,
        )

    def get_success_rate(
        self,
        operation_type: OperationType | None = None,
        batch_id: str | None = None,
    ) -> float:
        """Calculate success rate for operations.

        Args:
            operation_type: Optional filter by operation type
            batch_id: Optional filter by batch ID

        Returns:
            Success rate as a percentage (0-100)
        """
        filtered = self._filter_metrics(operation_type=operation_type, batch_id=batch_id)

        if not filtered:
            return 0.0

        success_count = sum(1 for m in filtered if m.status == OperationStatus.SUCCESS)
        return (success_count / len(filtered)) * 100

    def get_average_duration(
        self,
        operation_type: OperationType | None = None,
        batch_id: str | None = None,
    ) -> float:
        """Calculate average operation duration.

        Args:
            operation_type: Optional filter by operation type
            batch_id: Optional filter by batch ID

        Returns:
            Average duration in seconds
        """
        filtered = self._filter_metrics(operation_type=operation_type, batch_id=batch_id)

        if not filtered:
            return 0.0

        total_duration = sum(m.duration_seconds for m in filtered)
        return total_duration / len(filtered)

    def get_error_breakdown(
        self,
        operation_type: OperationType | None = None,
        batch_id: str | None = None,
    ) -> dict[str, int]:
        """Get breakdown of errors by type.

        Args:
            operation_type: Optional filter by operation type
            batch_id: Optional filter by batch ID

        Returns:
            Dictionary mapping error types to counts
        """
        filtered = self._filter_metrics(operation_type=operation_type, batch_id=batch_id)

        error_counts: dict[str, int] = {}
        for metric in filtered:
            if metric.status != OperationStatus.SUCCESS and metric.error_type:
                error_counts[metric.error_type] = error_counts.get(metric.error_type, 0) + 1

        return error_counts

    def get_operation_counts(
        self,
        batch_id: str | None = None,
    ) -> dict[str, dict[str, int]]:
        """Get operation counts by type and status.

        Args:
            batch_id: Optional filter by batch ID

        Returns:
            Dictionary mapping operation types to status counts
        """
        filtered = self._filter_metrics(batch_id=batch_id)

        counts: dict[str, dict[str, int]] = {}
        for metric in filtered:
            op_type = metric.operation_type.value
            status = metric.status.value

            if op_type not in counts:
                counts[op_type] = {}

            counts[op_type][status] = counts[op_type].get(status, 0) + 1

        return counts

    def get_summary(self, batch_id: str | None = None) -> dict[str, Any]:
        """Get comprehensive metrics summary.

        Args:
            batch_id: Optional filter by batch ID

        Returns:
            Summary dictionary with all key metrics
        """
        filtered = self._filter_metrics(batch_id=batch_id)

        if not filtered:
            return {
                "total_operations": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "operation_counts": {},
                "error_breakdown": {},
            }

        return {
            "total_operations": len(filtered),
            "success_rate": self.get_success_rate(batch_id=batch_id),
            "average_duration": self.get_average_duration(batch_id=batch_id),
            "operation_counts": self.get_operation_counts(batch_id=batch_id),
            "error_breakdown": self.get_error_breakdown(batch_id=batch_id),
        }

    def _filter_metrics(
        self,
        operation_type: OperationType | None = None,
        batch_id: str | None = None,
    ) -> list[OperationMetric]:
        """Filter metrics by criteria.

        Args:
            operation_type: Optional operation type filter
            batch_id: Optional batch ID filter

        Returns:
            Filtered list of metrics
        """
        filtered = self.metrics

        if operation_type:
            filtered = [m for m in filtered if m.operation_type == operation_type]

        if batch_id:
            filtered = [m for m in filtered if m.batch_id == batch_id]

        return filtered


# Global metrics collector instance
_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        MetricsCollector instance
    """
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


class timed_operation:
    """Context manager for timing operations.

    Usage:
        with timed_operation(OperationType.PRE_CHECK, cluster_id="cluster-1") as timer:
            # Perform operation
            ...
            if success:
                timer.success()
            else:
                timer.failure(error_type="CheckFailed", error_message="...")
    """

    def __init__(
        self,
        operation_type: OperationType,
        cluster_id: str | None = None,
        batch_id: str | None = None,
        **metadata: Any,
    ):
        """Initialize timed operation context.

        Args:
            operation_type: Type of operation
            cluster_id: Optional cluster ID
            batch_id: Optional batch ID
            **metadata: Additional metadata
        """
        self.operation_type = operation_type
        self.cluster_id = cluster_id
        self.batch_id = batch_id
        self.metadata = metadata
        self.start_time: float | None = None
        self.status: OperationStatus | None = None
        self.error_type: str | None = None
        self.error_message: str | None = None
        self.collector = get_metrics_collector()

    def __enter__(self) -> "timed_operation":
        """Start timing."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop timing and record metric."""
        if self.start_time is None:
            return

        duration = time.time() - self.start_time

        # Auto-detect failure from exception if not explicitly set
        if self.status is None:
            if exc_type is not None:
                self.status = OperationStatus.ERROR
                self.error_type = exc_type.__name__
                self.error_message = str(exc_val)
            else:
                self.status = OperationStatus.SUCCESS

        self.collector.record_operation(
            operation_type=self.operation_type,
            status=self.status,
            duration_seconds=duration,
            cluster_id=self.cluster_id,
            batch_id=self.batch_id,
            error_type=self.error_type,
            error_message=self.error_message,
            **self.metadata,
        )

    def success(self) -> None:
        """Mark operation as successful."""
        self.status = OperationStatus.SUCCESS

    def failure(
        self,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Mark operation as failed.

        Args:
            error_type: Type of error
            error_message: Error message
        """
        self.status = OperationStatus.FAILURE
        self.error_type = error_type
        self.error_message = error_message

    def timeout(self) -> None:
        """Mark operation as timed out."""
        self.status = OperationStatus.TIMEOUT
