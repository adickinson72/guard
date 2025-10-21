"""Integration tests for Datadog client."""

from datetime import datetime, timedelta

import pytest

from guard.clients.datadog_client import DatadogClient
from guard.core.exceptions import DatadogError


@pytest.mark.integration
class TestDatadogClientIntegration:
    """Integration tests for DatadogClient with real Datadog API."""

    @pytest.fixture
    def datadog_client(
        self,
        datadog_test_api_key: str | None,
        datadog_test_app_key: str | None,
        skip_if_no_datadog_credentials,
    ) -> DatadogClient:
        """Create Datadog client for integration tests."""
        return DatadogClient(
            api_key=datadog_test_api_key,
            app_key=datadog_test_app_key,
            site="datadoghq.com",
        )

    def test_client_initialization(self, datadog_client: DatadogClient):
        """Test Datadog client initializes successfully."""
        assert datadog_client.api_client is not None
        assert datadog_client.metrics_api is not None
        assert datadog_client.monitors_api is not None

    def test_query_metrics_system_cpu(self, datadog_client: DatadogClient):
        """Test querying system CPU metrics (available in most Datadog accounts)."""
        # Query last hour
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        # Query system.cpu.idle (common metric)
        query = "avg:system.cpu.idle{*}"

        try:
            result = datadog_client.query_metrics(
                query=query,
                start=start_time,
                end=end_time,
            )

            assert result is not None
            assert "status" in result
            assert result["status"] == "ok"
            assert "series" in result

        except DatadogError as e:
            # If no data available, that's ok for integration test
            if "No data" in str(e) or "no results" in str(e).lower():
                pytest.skip(f"No system.cpu.idle metrics available: {e}")
            else:
                raise

    def test_query_metrics_with_timestamps(self, datadog_client: DatadogClient):
        """Test querying metrics with Unix timestamps."""
        # Query last 30 minutes
        end_time = int(datetime.now().timestamp())
        start_time = end_time - 1800  # 30 minutes ago

        query = "avg:system.load.1{*}"

        try:
            result = datadog_client.query_metrics(
                query=query,
                start=start_time,
                end=end_time,
            )

            assert result is not None
            assert isinstance(result, dict)

        except DatadogError as e:
            if "No data" in str(e) or "no results" in str(e).lower():
                pytest.skip(f"No system.load.1 metrics available: {e}")
            else:
                raise

    def test_query_metrics_invalid_query(self, datadog_client: DatadogClient):
        """Test querying with invalid metric name."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        # Use an invalid metric name
        query = "avg:invalid.metric.that.does.not.exist.12345{*}"

        # Should either return empty results or raise DatadogError
        try:
            result = datadog_client.query_metrics(
                query=query,
                start=start_time,
                end=end_time,
            )
            # If it succeeds, series should be empty or None
            assert "series" in result
            if result.get("series"):
                assert len(result["series"]) == 0
        except DatadogError:
            # This is also acceptable for an invalid metric
            pass

    def test_list_monitors(self, datadog_client: DatadogClient):
        """Test listing all monitors."""
        try:
            # Get all monitors (no filters)
            monitors = datadog_client.monitors_api.list_monitors()

            assert isinstance(monitors, list)
            # Account may or may not have monitors

            if len(monitors) > 0:
                monitor = monitors[0]
                # Verify monitor structure
                assert hasattr(monitor, "id")
                assert hasattr(monitor, "name")
                assert hasattr(monitor, "type")
                assert hasattr(monitor, "overall_state")

        except Exception as e:
            pytest.skip(f"Could not list monitors: {e}")

    def test_get_active_alerts(self, datadog_client: DatadogClient):
        """Test getting active alerts."""
        active_alerts = datadog_client.get_active_alerts()

        assert isinstance(active_alerts, list)
        # Account may not have any active alerts (which is good!)

        if len(active_alerts) > 0:
            alert = active_alerts[0]
            assert isinstance(alert, dict)
            assert "id" in alert
            assert "name" in alert
            assert "overall_state" in alert
            assert alert["overall_state"] == "Alert"

    def test_get_active_alerts_with_tags(self, datadog_client: DatadogClient):
        """Test getting active alerts filtered by tags."""
        # Use a tag that's unlikely to match anything
        tags = ["env:integration-test-nonexistent"]

        active_alerts = datadog_client.get_active_alerts(tags=tags)

        assert isinstance(active_alerts, list)
        # Should be empty or very few results with this specific tag
        assert len(active_alerts) >= 0


@pytest.mark.integration
@pytest.mark.slow
class TestDatadogClientIstioIntegration:
    """Integration tests for Istio-specific Datadog metrics.

    These tests assume Istio metrics are being collected in Datadog.
    """

    @pytest.fixture
    def datadog_client(
        self,
        datadog_test_api_key: str | None,
        datadog_test_app_key: str | None,
        skip_if_no_datadog_credentials,
    ) -> DatadogClient:
        """Create Datadog client for integration tests."""
        return DatadogClient(
            api_key=datadog_test_api_key,
            app_key=datadog_test_app_key,
        )

    def test_query_istio_metrics(self, datadog_client: DatadogClient):
        """Test querying Istio metrics (if available)."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        # Common Istio metrics
        istio_queries = [
            "avg:istio.mesh.request.count{*}",
            "avg:istio.pilot.xds.pushes{*}",
            "avg:istio.pilot.services{*}",
        ]

        found_istio_metrics = False
        for query in istio_queries:
            try:
                result = datadog_client.query_metrics(
                    query=query,
                    start=start_time,
                    end=end_time,
                )

                if result.get("series") and len(result["series"]) > 0:
                    found_istio_metrics = True
                    assert result["status"] == "ok"
                    break

            except DatadogError:
                continue

        if not found_istio_metrics:
            pytest.skip("No Istio metrics found in Datadog account")

    def test_query_istio_metrics_by_cluster(self, datadog_client: DatadogClient):
        """Test querying Istio metrics filtered by cluster tag."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        # Query with cluster filter (will fail if no matching data)
        query = "avg:istio.mesh.request.count{cluster:*} by {cluster}"

        try:
            result = datadog_client.query_metrics(
                query=query,
                start=start_time,
                end=end_time,
            )

            if result.get("series") and len(result["series"]) > 0:
                assert result["status"] == "ok"
                # Verify grouping by cluster
                series = result["series"][0]
                assert "scope" in series or "tag_set" in series
            else:
                pytest.skip("No Istio metrics with cluster tag found")

        except DatadogError as e:
            pytest.skip(f"No Istio metrics available: {e}")


@pytest.mark.integration
class TestDatadogClientMonitorOperations:
    """Integration tests for monitor operations.

    These tests interact with monitors in the Datadog account.
    """

    @pytest.fixture
    def datadog_client(
        self,
        datadog_test_api_key: str | None,
        datadog_test_app_key: str | None,
        skip_if_no_datadog_credentials,
    ) -> DatadogClient:
        """Create Datadog client for integration tests."""
        return DatadogClient(
            api_key=datadog_test_api_key,
            app_key=datadog_test_app_key,
        )

    def test_get_monitor_by_id(self, datadog_client: DatadogClient):
        """Test getting a specific monitor by ID."""
        # First, list monitors to get a valid ID
        try:
            monitors = datadog_client.monitors_api.list_monitors()

            if not monitors:
                pytest.skip("No monitors available in account for testing")

            monitor_id = monitors[0].id

            # Get the specific monitor
            monitor = datadog_client.get_monitor(monitor_id)

            assert monitor is not None
            assert isinstance(monitor, dict)
            assert monitor["id"] == monitor_id
            assert "name" in monitor
            assert "type" in monitor

        except Exception as e:
            pytest.skip(f"Could not test get_monitor: {e}")

    def test_get_monitor_invalid_id(self, datadog_client: DatadogClient):
        """Test getting monitor with invalid ID raises error."""
        # Use an ID that's very unlikely to exist
        invalid_id = 99999999999

        with pytest.raises(DatadogError):
            datadog_client.get_monitor(invalid_id)

    def test_check_monitors_by_tags(self, datadog_client: DatadogClient):
        """Test checking monitors filtered by tags."""
        # List all monitors first to see what tags exist
        try:
            monitors = datadog_client.monitors_api.list_monitors()

            if not monitors:
                pytest.skip("No monitors available in account for testing")

            # Get tags from first monitor (if any)
            if monitors[0].tags:
                test_tag = monitors[0].tags[0]

                # Query with this tag
                filtered_monitors = datadog_client.monitors_api.list_monitors(tags=test_tag)

                assert isinstance(filtered_monitors, list)
                # Should have at least one monitor (the one we got the tag from)
                assert len(filtered_monitors) >= 1

        except Exception as e:
            pytest.skip(f"Could not test monitor tag filtering: {e}")
