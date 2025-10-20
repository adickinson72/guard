"""Metrics provider interface for monitoring systems."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MetricPoint:
    """A single metric data point."""

    timestamp: datetime
    value: float
    tags: dict[str, str]


class MetricsProvider(ABC):
    """Abstract interface for metrics query operations.

    This interface abstracts metrics providers (Datadog, Prometheus, etc.)
    providing a unified way to query time-series data and check system health.

    Design Philosophy:
    - Hides provider-specific query syntax where possible
    - Returns normalized data structures
    - Provides both raw metrics and computed statistics
    """

    @abstractmethod
    async def query_timeseries(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        tags: dict[str, str] | None = None,
        aggregation: str | None = None,
    ) -> list[MetricPoint]:
        """Query time-series metric data.

        Args:
            metric_name: Name of the metric to query
            start_time: Start of time range
            end_time: End of time range
            tags: Optional tags to filter by
            aggregation: Optional aggregation function (avg, sum, max, min)

        Returns:
            List of metric points

        Raises:
            MetricsProviderError: If query fails
        """

    @abstractmethod
    async def query_scalar(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        tags: dict[str, str] | None = None,
        aggregation: str = "avg",
    ) -> float:
        """Query a single scalar value from a metric.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            tags: Optional tags to filter by
            aggregation: Aggregation function (default: avg)

        Returns:
            Single aggregated value

        Raises:
            MetricsProviderError: If query fails
        """

    @abstractmethod
    async def query_statistics(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        tags: dict[str, str] | None = None,
    ) -> dict[str, float]:
        """Get statistical summary of a metric.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            tags: Optional tags to filter by

        Returns:
            Dictionary with keys: min, max, avg, last, count

        Raises:
            MetricsProviderError: If query fails
        """

    @abstractmethod
    async def check_active_alerts(
        self, tags: dict[str, str] | None = None
    ) -> tuple[bool, list[dict[str, any]]]:
        """Check for active alerts/monitors.

        Args:
            tags: Optional tags to filter alerts

        Returns:
            Tuple of (healthy, list of active alert details)
            healthy=True means no active alerts

        Raises:
            MetricsProviderError: If check fails
        """

    @abstractmethod
    async def get_monitor_status(self, monitor_id: str) -> dict[str, any]:
        """Get status of a specific monitor.

        Args:
            monitor_id: Monitor identifier

        Returns:
            Dictionary with monitor status details

        Raises:
            MetricsProviderError: If retrieval fails
        """

    @abstractmethod
    async def query_raw(
        self, query: str, start_time: datetime, end_time: datetime
    ) -> dict[str, any]:
        """Execute a raw provider-specific query.

        This is an escape hatch for provider-specific functionality
        that doesn't fit the normalized interface.

        Args:
            query: Provider-specific query string
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Raw query results (provider-specific format)

        Raises:
            MetricsProviderError: If query fails
        """
