"""Unit tests for DatadogAdapter.

Tests the Datadog adapter implementation of MetricsProvider interface.
All Datadog API calls are mocked to ensure tests are isolated and fast.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from guard.adapters.datadog_adapter import DatadogAdapter
from guard.interfaces.exceptions import MetricsProviderError
from guard.interfaces.metrics_provider import MetricPoint


class TestDatadogAdapterInit:
    """Tests for DatadogAdapter initialization."""

    @patch("guard.adapters.datadog_adapter.DatadogClient")
    def test_init_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test successful adapter initialization."""
        mock_client = MagicMock()
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(
            api_key="test-api-key", app_key="test-app-key", site="datadoghq.com"
        )

        mock_datadog_client_class.assert_called_once_with(
            api_key="test-api-key", app_key="test-app-key", site="datadoghq.com"
        )
        assert adapter.client == mock_client

    @patch("guard.adapters.datadog_adapter.DatadogClient")
    def test_init_with_custom_site(self, mock_datadog_client_class: MagicMock) -> None:
        """Test initialization with custom Datadog site."""
        mock_client = MagicMock()
        mock_datadog_client_class.return_value = mock_client

        DatadogAdapter(api_key="test-api-key", app_key="test-app-key", site="datadoghq.eu")

        mock_datadog_client_class.assert_called_once_with(
            api_key="test-api-key", app_key="test-app-key", site="datadoghq.eu"
        )

    @patch("guard.adapters.datadog_adapter.DatadogClient")
    def test_init_failure_raises_metrics_provider_error(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test initialization failure raises MetricsProviderError."""
        mock_datadog_client_class.side_effect = Exception("Invalid API key")

        with pytest.raises(MetricsProviderError) as exc_info:
            DatadogAdapter(api_key="bad-key", app_key="bad-app-key")

        assert "Failed to initialize Datadog adapter" in str(exc_info.value)


class TestDatadogAdapterQueryTimeseries:
    """Tests for query_timeseries method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_timeseries_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test successful timeseries query."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {
            "status": "ok",
            "series": [
                {
                    "metric": "istio.request.duration.p95",
                    "scope": "cluster:test-cluster,service:istio-system",
                    "pointlist": [[1704067200000, 125.5], [1704067260000, 130.2]],
                }
            ],
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_timeseries(
            metric_name="istio.request.duration.p95",
            start_time=start_time,
            end_time=end_time,
            tags={"cluster": "test-cluster", "service": "istio-system"},
            aggregation="avg",
        )

        # Verify query was built correctly
        expected_query = "avg:istio.request.duration.p95{cluster:test-cluster,service:istio-system}"
        mock_client.query_metrics.assert_called_once_with(expected_query, start_time, end_time)

        # Verify results
        assert len(result) == 2
        assert isinstance(result[0], MetricPoint)
        assert result[0].value == 125.5
        assert result[0].tags["cluster"] == "test-cluster"
        assert result[0].tags["service"] == "istio-system"

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_timeseries_no_tags(self, mock_datadog_client_class: MagicMock) -> None:
        """Test timeseries query without tags."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {
            "status": "ok",
            "series": [{"metric": "system.cpu.usage", "pointlist": [[1704067200000, 45.3]]}],
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_timeseries(
            metric_name="system.cpu.usage", start_time=start_time, end_time=end_time
        )

        # Query should not have tag filter
        expected_query = "avg:system.cpu.usage"
        mock_client.query_metrics.assert_called_once_with(expected_query, start_time, end_time)

        assert len(result) == 1
        assert result[0].value == 45.3

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_timeseries_empty_result(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test timeseries query with no data points."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {"status": "ok", "series": []}
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_timeseries(
            metric_name="nonexistent.metric", start_time=start_time, end_time=end_time
        )

        assert result == []

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_timeseries_filters_null_values(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test that null values are filtered from results."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {
            "status": "ok",
            "series": [
                {
                    "metric": "test.metric",
                    "pointlist": [
                        [1704067200000, 10.0],
                        [1704067260000, None],  # Null value should be filtered
                        [1704067320000, 20.0],
                    ],
                }
            ],
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_timeseries(
            metric_name="test.metric", start_time=start_time, end_time=end_time
        )

        # Should only have 2 points (null filtered out)
        assert len(result) == 2
        assert result[0].value == 10.0
        assert result[1].value == 20.0

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_timeseries_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test timeseries query failure raises MetricsProviderError."""
        mock_client = MagicMock()
        mock_client.query_metrics.side_effect = Exception("API error")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.query_timeseries(
                metric_name="test.metric", start_time=datetime.now(), end_time=datetime.now()
            )

        assert "Failed to query timeseries" in str(exc_info.value)


class TestDatadogAdapterQueryScalar:
    """Tests for query_scalar method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_scalar_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test successful scalar query (averages all points)."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {
            "status": "ok",
            "series": [
                {
                    "metric": "test.metric",
                    "pointlist": [
                        [1704067200000, 10.0],
                        [1704067260000, 20.0],
                        [1704067320000, 30.0],
                    ],
                }
            ],
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_scalar(
            metric_name="test.metric", start_time=start_time, end_time=end_time, aggregation="avg"
        )

        # Should return average of all points: (10 + 20 + 30) / 3 = 20.0
        assert result == 20.0

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_scalar_no_data_returns_zero(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test scalar query with no data returns 0.0."""
        mock_client = MagicMock()
        mock_client.query_metrics.return_value = {"status": "ok", "series": []}
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_scalar(
            metric_name="nonexistent.metric", start_time=datetime.now(), end_time=datetime.now()
        )

        assert result == 0.0

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_scalar_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test scalar query failure raises MetricsProviderError."""
        mock_client = MagicMock()
        mock_client.query_metrics.side_effect = Exception("API error")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.query_scalar(
                metric_name="test.metric", start_time=datetime.now(), end_time=datetime.now()
            )

        assert "Failed to query scalar" in str(exc_info.value)


class TestDatadogAdapterQueryStatistics:
    """Tests for query_statistics method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_statistics_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test successful statistics query."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        mock_client.get_metric_statistics.return_value = {
            "min": 10.0,
            "max": 30.0,
            "avg": 20.0,
            "last": 25.0,
        }
        mock_client.query_metrics.return_value = {
            "status": "ok",
            "series": [
                {
                    "metric": "test.metric",
                    "pointlist": [
                        [1704067200000, 10.0],
                        [1704067260000, 20.0],
                        [1704067320000, 30.0],
                    ],
                }
            ],
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_statistics(
            metric_name="test.metric",
            start_time=start_time,
            end_time=end_time,
            tags={"cluster": "test"},
        )

        assert result["min"] == 10.0
        assert result["max"] == 30.0
        assert result["avg"] == 20.0
        assert result["last"] == 25.0
        assert result["count"] == 3.0  # 3 data points

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_statistics_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test statistics query failure raises MetricsProviderError."""
        mock_client = MagicMock()
        mock_client.get_metric_statistics.side_effect = Exception("API error")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.query_statistics(
                metric_name="test.metric", start_time=datetime.now(), end_time=datetime.now()
            )

        assert "Failed to query statistics" in str(exc_info.value)


class TestDatadogAdapterCheckActiveAlerts:
    """Tests for check_active_alerts method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_check_active_alerts_no_alerts(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test checking alerts when none are active."""
        mock_client = MagicMock()
        mock_client.check_monitor_health.return_value = (True, [])
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        healthy, alerts = await adapter.check_active_alerts()

        assert healthy is True
        assert alerts == []
        mock_client.check_monitor_health.assert_called_once_with(tags=None)

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_check_active_alerts_with_alerts(
        self, mock_datadog_client_class: MagicMock
    ) -> None:
        """Test checking alerts when some are active."""
        mock_client = MagicMock()
        mock_client.check_monitor_health.return_value = (
            False,
            [
                {"id": 123, "name": "High CPU", "status": "alert"},
                {"id": 456, "name": "High Memory", "status": "warn"},
            ],
        )
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        healthy, alerts = await adapter.check_active_alerts(
            tags={"cluster": "prod", "service": "api"}
        )

        assert healthy is False
        assert len(alerts) == 2
        assert alerts[0]["name"] == "High CPU"
        assert alerts[1]["name"] == "High Memory"

        # Verify tags were converted to list format
        mock_client.check_monitor_health.assert_called_once_with(
            tags=["cluster:prod", "service:api"]
        )

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_check_active_alerts_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test check alerts failure raises MetricsProviderError."""
        mock_client = MagicMock()
        mock_client.check_monitor_health.side_effect = Exception("API error")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.check_active_alerts()

        assert "Failed to check active alerts" in str(exc_info.value)


class TestDatadogAdapterGetMonitorStatus:
    """Tests for get_monitor_status method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_get_monitor_status_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test successful monitor status retrieval."""
        mock_client = MagicMock()
        mock_client.get_monitor.return_value = {
            "id": 12345,
            "name": "API Latency",
            "type": "metric alert",
            "query": "avg(last_5m):avg:api.latency{*} > 500",
            "overall_state": "OK",
        }
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.get_monitor_status("12345")

        mock_client.get_monitor.assert_called_once_with(12345)
        assert result["id"] == 12345
        assert result["name"] == "API Latency"
        assert result["overall_state"] == "OK"

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_get_monitor_status_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test monitor status retrieval failure."""
        mock_client = MagicMock()
        mock_client.get_monitor.side_effect = Exception("Monitor not found")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.get_monitor_status("99999")

        assert "Failed to get monitor status" in str(exc_info.value)


class TestDatadogAdapterQueryRaw:
    """Tests for query_raw method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_raw_success(self, mock_datadog_client_class: MagicMock) -> None:
        """Test raw query returns unprocessed results."""
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        end_time = datetime(2024, 1, 1, 1, 0, 0)

        mock_client = MagicMock()
        raw_response = {
            "status": "ok",
            "res_type": "time_series",
            "series": [{"metric": "custom.metric", "pointlist": [[1704067200000, 42.0]]}],
            "from_date": 1704067200000,
            "to_date": 1704070800000,
        }
        mock_client.query_metrics.return_value = raw_response
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        result = await adapter.query_raw(
            query="sum:custom.metric{*}.rollup(sum, 3600)", start_time=start_time, end_time=end_time
        )

        assert result == raw_response
        mock_client.query_metrics.assert_called_once_with(
            "sum:custom.metric{*}.rollup(sum, 3600)", start_time, end_time
        )

    @pytest.mark.asyncio
    @patch("guard.adapters.datadog_adapter.DatadogClient")
    async def test_query_raw_failure(self, mock_datadog_client_class: MagicMock) -> None:
        """Test raw query failure raises MetricsProviderError."""
        mock_client = MagicMock()
        mock_client.query_metrics.side_effect = Exception("Invalid query syntax")
        mock_datadog_client_class.return_value = mock_client

        adapter = DatadogAdapter(api_key="test", app_key="test")

        with pytest.raises(MetricsProviderError) as exc_info:
            await adapter.query_raw(
                query="invalid{query", start_time=datetime.now(), end_time=datetime.now()
            )

        assert "Failed to execute raw query" in str(exc_info.value)
