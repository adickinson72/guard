"""Unit tests for cluster registry atomic operations."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError
from guard.core.models import ClusterStatus
from guard.registry.cluster_registry import ClusterRegistry


class TestClusterRegistryAtomicOperations:
    """Test atomic status updates in cluster registry."""

    @patch("guard.registry.cluster_registry.boto3")
    def test_atomic_status_update_success(self, mock_boto3):
        """Test successful atomic status update."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value.Table.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        # Mock successful transaction
        mock_client.transact_write_items.return_value = {}

        result = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
        )

        assert result is True

        # Verify transaction was called with correct parameters
        call_args = mock_client.transact_write_items.call_args
        transact_items = call_args[1]["TransactItems"]

        assert len(transact_items) == 1
        update_item = transact_items[0]["Update"]

        # Verify UpdateExpression starts with "SET "
        assert update_item["UpdateExpression"].startswith("SET ")

        # Verify proper type descriptors
        attr_values = update_item["ExpressionAttributeValues"]
        assert attr_values[":new_status"] == {"S": "upgrading"}
        assert attr_values[":expected_status"] == {"S": "pending"}
        assert attr_values[":one"] == {"N": "1"}

    @patch("guard.registry.cluster_registry.boto3")
    def test_atomic_status_update_fails_on_mismatch(self, mock_boto3):
        """Test atomic update fails when status doesn't match."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value.Table.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        # Mock transaction cancellation (status mismatch)
        mock_client.exceptions.TransactionCanceledException = Exception
        mock_client.transact_write_items.side_effect = (
            mock_client.exceptions.TransactionCanceledException()
        )

        result = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
        )

        assert result is False

    @patch("guard.registry.cluster_registry.boto3")
    def test_atomic_update_with_additional_fields(self, mock_boto3):
        """Test atomic update with additional metadata fields."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value.Table.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        mock_client.transact_write_items.return_value = {}

        result = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
            istio_version="1.20.0",
            upgraded_by="admin",
        )

        assert result is True

        # Verify additional fields in update
        call_args = mock_client.transact_write_items.call_args
        update_expr = call_args[1]["TransactItems"][0]["Update"]["UpdateExpression"]

        assert "istio_version = :istio_version" in update_expr
        assert "upgraded_by = :upgraded_by" in update_expr

        attr_values = call_args[1]["TransactItems"][0]["Update"]["ExpressionAttributeValues"]
        assert attr_values[":istio_version"] == {"S": "1.20.0"}
        assert attr_values[":upgraded_by"] == {"S": "admin"}

    @patch("guard.registry.cluster_registry.boto3")
    def test_atomic_update_type_marshalling(self, mock_boto3):
        """Test correct DynamoDB type marshalling for different value types."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value.Table.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        mock_client.transact_write_items.return_value = {}

        result = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
            retry_count=3,  # int
            auto_rollback=True,  # bool
            version_tag="1.20",  # str
            duration=123.45,  # float
        )

        assert result is True

        # Capture call_args from the mock
        call_args = mock_client.transact_write_items.call_args
        attr_values = call_args[1]["TransactItems"][0]["Update"]["ExpressionAttributeValues"]

        # Verify correct type descriptors
        assert attr_values[":retry_count"] == {"N": "3"}
        assert attr_values[":auto_rollback"] == {"BOOL": True}
        assert attr_values[":version_tag"] == {"S": "1.20"}
        assert attr_values[":duration"] == {"N": "123.45"}

    @patch("guard.registry.cluster_registry.boto3")
    def test_atomic_update_prevents_race_condition(self, mock_boto3):
        """Test atomic update prevents race conditions."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value.Table.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        # Simulate race condition: two processes try to update simultaneously
        # First succeeds
        mock_client.transact_write_items.return_value = {}
        result1 = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
        )
        assert result1 is True

        # Second fails (status already changed)
        mock_client.exceptions.TransactionCanceledException = Exception
        mock_client.transact_write_items.side_effect = (
            mock_client.exceptions.TransactionCanceledException()
        )

        result2 = registry.update_cluster_status_atomic(
            cluster_id="cluster-1",
            expected_status="pending",
            new_status="upgrading",
        )
        assert result2 is False


class TestClusterRegistryBatchPrerequisites:
    """Test batch prerequisite validation."""

    @patch("guard.registry.cluster_registry.boto3")
    def test_batch_prerequisites_no_prerequisites(self, mock_boto3):
        """Test validation passes when no prerequisites defined."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_boto3.client.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        batch_order = {}  # No prerequisites

        valid, message = registry.validate_batch_prerequisites("batch-1", batch_order)

        assert valid is True
        assert "No prerequisites" in message

    @patch("guard.registry.cluster_registry.boto3")
    def test_batch_prerequisites_all_healthy(self, mock_boto3):
        """Test validation passes when all prerequisite clusters are healthy."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_boto3.client.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        # Mock prerequisite batch with healthy clusters
        from guard.core.models import ClusterConfig, DatadogTags

        healthy_cluster = ClusterConfig(
            cluster_id="cluster-1",
            cluster_name="test-cluster",
            region="us-east-1",
            environment="test",
            batch_id="batch-0",
            status=ClusterStatus.HEALTHY,
            gitlab_repo="test/repo",
            flux_config_path="/configs/test",
            aws_role_arn="arn:aws:iam::123456789012:role/test",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="test-cluster", env="test"),
            owner_team="test-team",
            owner_handle="test@example.com",
        )

        registry.get_clusters_by_batch = MagicMock(return_value=[healthy_cluster])

        batch_order = {"batch-1": ["batch-0"]}

        valid, message = registry.validate_batch_prerequisites("batch-1", batch_order)

        assert valid is True
        assert "All prerequisites met" in message

    @patch("guard.registry.cluster_registry.boto3")
    def test_batch_prerequisites_unhealthy_cluster(self, mock_boto3):
        """Test validation fails when prerequisite cluster is not healthy."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table
        mock_boto3.client.return_value = MagicMock()

        registry = ClusterRegistry("test-table", region="us-east-1")

        from guard.core.models import ClusterConfig, DatadogTags

        # Mock prerequisite batch with failed cluster
        failed_cluster = ClusterConfig(
            cluster_id="cluster-1",
            cluster_name="test-cluster",
            region="us-east-1",
            environment="test",
            batch_id="batch-0",
            status=ClusterStatus.FAILED_UPGRADE_ROLLED_BACK,
            gitlab_repo="test/repo",
            flux_config_path="/configs/test",
            aws_role_arn="arn:aws:iam::123456789012:role/test",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="test-cluster", env="test"),
            owner_team="test-team",
            owner_handle="test@example.com",
        )

        registry.get_clusters_by_batch = MagicMock(return_value=[failed_cluster])

        batch_order = {"batch-1": ["batch-0"]}

        valid, message = registry.validate_batch_prerequisites("batch-1", batch_order)

        assert valid is False
        assert "not completed" in message
        assert "cluster-1" in message
