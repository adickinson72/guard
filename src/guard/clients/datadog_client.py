"""Datadog client for metrics and monitoring operations."""

from datetime import datetime
from typing import Any

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.exceptions import ApiException
from datadog_api_client.model_utils import UnsetType
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.api.monitors_api import MonitorsApi

from guard.core.exceptions import DatadogError
from guard.utils.logging import get_logger
from guard.utils.rate_limiter import rate_limited
from guard.utils.retry import retry_on_exception

logger = get_logger(__name__)


class DatadogClient:
    """Datadog API client wrapper."""

    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com"):
        """Initialize Datadog client.

        Args:
            api_key: Datadog API key
            app_key: Datadog application key
            site: Datadog site (e.g., datadoghq.com, datadoghq.eu)
        """
        self.api_key = api_key
        self.app_key = app_key
        self.site = site

        # Configure API client
        configuration = Configuration()
        configuration.api_key["apiKeyAuth"] = api_key
        configuration.api_key["appKeyAuth"] = app_key
        configuration.server_variables["site"] = site

        self.api_client = ApiClient(configuration)
        self.metrics_api = MetricsApi(self.api_client)
        self.monitors_api = MonitorsApi(self.api_client)

        logger.debug("datadog_client_initialized", site=site)

    @rate_limited("datadog_api")
    @retry_on_exception(exceptions=(ApiException,), max_attempts=3)
    def query_metrics(
        self,
        query: str,
        start: int | datetime,
        end: int | datetime,
    ) -> dict[str, Any]:
        """Query Datadog metrics.

        Args:
            query: Datadog metrics query string
            start: Start time (Unix timestamp or datetime)
            end: End time (Unix timestamp or datetime)

        Returns:
            Query results dictionary

        Raises:
            DatadogError: If query fails
        """
        try:
            # Convert datetime to Unix timestamp if needed
            start_ts = int(start.timestamp()) if isinstance(start, datetime) else start

            end_ts = int(end.timestamp()) if isinstance(end, datetime) else end

            logger.debug(
                "querying_metrics",
                query=query,
                start=start_ts,
                end=end_ts,
            )

            response = self.metrics_api.query_metrics(
                _from=start_ts,
                to=end_ts,
                query=query,
            )

            logger.info("metrics_queried_successfully", query=query)
            return response.to_dict()

        except ApiException as e:
            logger.error(
                "metrics_query_failed",
                query=query,
                status=e.status,
                reason=e.reason,
            )
            raise DatadogError(f"Failed to query metrics: {e.reason}") from e

    @rate_limited("datadog_api")
    @retry_on_exception(exceptions=(ApiException,), max_attempts=3)
    def get_active_alerts(self, tags: list[str] | None = None) -> list[dict[str, Any]]:
        """Get active monitors (alerts).

        Args:
            tags: Filter by tags (e.g., ["cluster:prod", "env:production"])

        Returns:
            List of active monitor dictionaries

        Raises:
            DatadogError: If retrieval fails
        """
        try:
            logger.debug("getting_active_alerts", tags=tags)

            # Build tags query - use UnsetType for None
            tags_query: str | UnsetType = ",".join(tags) if tags else UnsetType.unset

            # List all monitors
            monitors = self.monitors_api.list_monitors(
                tags=tags_query,
            )

            # Filter for alerts (overall_state == "Alert")
            active_alerts = [m.to_dict() for m in monitors if m.overall_state == "Alert"]

            logger.info("active_alerts_retrieved", count=len(active_alerts))
            return active_alerts

        except ApiException as e:
            logger.error(
                "get_active_alerts_failed",
                status=e.status,
                reason=e.reason,
            )
            raise DatadogError(f"Failed to get active alerts: {e.reason}") from e

    @rate_limited("datadog_api")
    @retry_on_exception(exceptions=(ApiException,), max_attempts=3)
    def get_monitor(self, monitor_id: int) -> dict[str, Any]:
        """Get a specific monitor by ID.

        Args:
            monitor_id: Monitor ID

        Returns:
            Monitor dictionary

        Raises:
            DatadogError: If retrieval fails
        """
        try:
            logger.debug("getting_monitor", monitor_id=monitor_id)

            monitor = self.monitors_api.get_monitor(monitor_id=monitor_id)

            logger.info("monitor_retrieved", monitor_id=monitor_id)
            return monitor.to_dict()

        except ApiException as e:
            logger.error(
                "get_monitor_failed",
                monitor_id=monitor_id,
                status=e.status,
            )
            raise DatadogError(f"Failed to get monitor {monitor_id}: {e.reason}") from e

    @rate_limited("datadog_api")
    @retry_on_exception(exceptions=(ApiException, DatadogError), max_attempts=3)
    def check_monitor_health(
        self, tags: list[str] | None = None
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Check if there are any active alerts.

        Args:
            tags: Filter by tags

        Returns:
            Tuple of (healthy: bool, active_alerts: list)
        """
        try:
            active_alerts = self.get_active_alerts(tags=tags)
            healthy = len(active_alerts) == 0

            logger.info(
                "monitor_health_check",
                healthy=healthy,
                alert_count=len(active_alerts),
            )

            return healthy, active_alerts

        except Exception as e:
            logger.error("monitor_health_check_failed", error=str(e))
            raise DatadogError("Failed to check monitor health") from e

    @rate_limited("datadog_api")
    @retry_on_exception(exceptions=(ApiException, DatadogError), max_attempts=3)
    def get_metric_statistics(
        self,
        query: str,
        start: int | datetime,
        end: int | datetime,
    ) -> dict[str, float]:
        """Get basic statistics for a metric query.

        Args:
            query: Datadog metrics query
            start: Start time
            end: End time

        Returns:
            Dictionary with min, max, avg, last values

        Raises:
            DatadogError: If query fails
        """
        try:
            result = self.query_metrics(query, start, end)

            # Extract series data
            series = result.get("series", [])
            if not series:
                logger.warning("no_metric_data", query=query)
                return {"min": 0.0, "max": 0.0, "avg": 0.0, "last": 0.0}

            # Combine all pointlists
            all_points = []
            for s in series:
                pointlist = s.get("pointlist", [])
                # pointlist is [[timestamp, value], ...]
                all_points.extend([p[1] for p in pointlist if p[1] is not None])

            if not all_points:
                return {"min": 0.0, "max": 0.0, "avg": 0.0, "last": 0.0}

            stats = {
                "min": min(all_points),
                "max": max(all_points),
                "avg": sum(all_points) / len(all_points),
                "last": all_points[-1],
            }

            logger.info("metric_statistics_calculated", query=query, stats=stats)
            return stats

        except Exception as e:
            logger.error("metric_statistics_failed", query=query, error=str(e))
            raise DatadogError(f"Failed to get metric statistics: {e}") from e
