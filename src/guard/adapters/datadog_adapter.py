"""Datadog adapter implementing MetricsProvider interface."""

from datetime import datetime

from guard.clients.datadog_client import DatadogClient
from guard.interfaces.exceptions import MetricsProviderError
from guard.interfaces.metrics_provider import MetricPoint, MetricsProvider
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class DatadogAdapter(MetricsProvider):
    """Adapter wrapping DatadogClient to implement MetricsProvider interface.

    This adapter normalizes Datadog API responses and provides a clean
    interface for querying metrics, hiding Datadog-specific details.
    """

    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com"):
        """Initialize Datadog adapter.

        Args:
            api_key: Datadog API key
            app_key: Datadog application key
            site: Datadog site
        """
        try:
            self.client = DatadogClient(api_key=api_key, app_key=app_key, site=site)
            logger.debug("datadog_adapter_initialized", site=site)
        except Exception as e:
            raise MetricsProviderError(f"Failed to initialize Datadog adapter: {e}") from e

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
            aggregation: Optional aggregation function

        Returns:
            List of metric points

        Raises:
            MetricsProviderError: If query fails
        """
        try:
            # Build Datadog query
            tag_filter = ""
            if tags:
                tag_parts = [f"{k}:{v}" for k, v in tags.items()]
                tag_filter = "{" + ",".join(tag_parts) + "}"

            agg = aggregation or "avg"
            query = f"{agg}:{metric_name}{tag_filter}"

            # Execute query
            result = self.client.query_metrics(query, start_time, end_time)

            # Parse series data into MetricPoint objects
            metric_points = []
            series = result.get("series", [])

            for s in series:
                pointlist = s.get("pointlist", [])
                series_tags = {}
                if s.get("scope"):
                    # Parse scope string like "cluster:prod-1,service:istio"
                    for tag_pair in s["scope"].split(","):
                        if ":" in tag_pair:
                            key, value = tag_pair.split(":", 1)
                            series_tags[key] = value

                for point in pointlist:
                    timestamp_ms, value = point
                    if value is not None:
                        metric_points.append(
                            MetricPoint(
                                timestamp=datetime.fromtimestamp(timestamp_ms / 1000),
                                value=float(value),
                                tags=series_tags,
                            )
                        )

            return metric_points

        except Exception as e:
            logger.error("query_timeseries_failed", metric_name=metric_name, error=str(e))
            raise MetricsProviderError(f"Failed to query timeseries: {e}") from e

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
        try:
            points = await self.query_timeseries(
                metric_name, start_time, end_time, tags, aggregation
            )

            if not points:
                return 0.0

            # Average all points
            return sum(p.value for p in points) / len(points)

        except Exception as e:
            logger.error("query_scalar_failed", metric_name=metric_name, error=str(e))
            raise MetricsProviderError(f"Failed to query scalar: {e}") from e

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
        try:
            # Build Datadog query
            tag_filter = ""
            if tags:
                tag_parts = [f"{k}:{v}" for k, v in tags.items()]
                tag_filter = "{" + ",".join(tag_parts) + "}"

            query = f"{metric_name}{tag_filter}"

            # Use client method
            stats = self.client.get_metric_statistics(query, start_time, end_time)

            # Add count
            points = await self.query_timeseries(metric_name, start_time, end_time, tags, None)
            stats["count"] = float(len(points))

            return stats

        except Exception as e:
            logger.error("query_statistics_failed", metric_name=metric_name, error=str(e))
            raise MetricsProviderError(f"Failed to query statistics: {e}") from e

    async def check_active_alerts(
        self, tags: dict[str, str] | None = None
    ) -> tuple[bool, list[dict[str, any]]]:
        """Check for active alerts/monitors.

        Args:
            tags: Optional tags to filter alerts

        Returns:
            Tuple of (healthy, list of active alert details)

        Raises:
            MetricsProviderError: If check fails
        """
        try:
            tag_list = None
            if tags:
                tag_list = [f"{k}:{v}" for k, v in tags.items()]

            healthy, alerts = self.client.check_monitor_health(tags=tag_list)
            return healthy, alerts

        except Exception as e:
            logger.error("check_active_alerts_failed", error=str(e))
            raise MetricsProviderError(f"Failed to check active alerts: {e}") from e

    async def get_monitor_status(self, monitor_id: str) -> dict[str, any]:
        """Get status of a specific monitor.

        Args:
            monitor_id: Monitor identifier

        Returns:
            Dictionary with monitor status details

        Raises:
            MetricsProviderError: If retrieval fails
        """
        try:
            return self.client.get_monitor(int(monitor_id))
        except Exception as e:
            logger.error("get_monitor_status_failed", monitor_id=monitor_id, error=str(e))
            raise MetricsProviderError(f"Failed to get monitor status: {e}") from e

    async def query_raw(
        self, query: str, start_time: datetime, end_time: datetime
    ) -> dict[str, any]:
        """Execute a raw Datadog query.

        Args:
            query: Datadog query string
            start_time: Start of time range
            end_time: End of time range

        Returns:
            Raw query results

        Raises:
            MetricsProviderError: If query fails
        """
        try:
            return self.client.query_metrics(query, start_time, end_time)
        except Exception as e:
            logger.error("query_raw_failed", query=query, error=str(e))
            raise MetricsProviderError(f"Failed to execute raw query: {e}") from e
