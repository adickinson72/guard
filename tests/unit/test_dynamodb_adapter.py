"""Unit tests for DynamoDBAdapter.

Tests the DynamoDB adapter implementation of StateStore interface.
All boto3 DynamoDB calls are mocked to ensure tests are isolated and fast.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from guard.adapters.dynamodb_adapter import DynamoDBAdapter
from guard.core.models import ClusterConfig, ClusterStatus
from guard.interfaces.exceptions import StateStoreError


class TestDynamoDBAdapterInit:
    """Tests for DynamoDBAdapter initialization."""

    @patch("guard.adapters.dynamodb_adapter.boto3")
    def test_init_success(self, mock_boto3: MagicMock) -> None:
        """Test successful adapter initialization."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="guard-cluster-registry", region="us-east-1")

        mock_boto3.resource.assert_called_once_with("dynamodb", region_name="us-east-1")
        mock_dynamodb.Table.assert_called_once_with("guard-cluster-registry")
        assert adapter.table_name == "guard-cluster-registry"
        assert adapter.region == "us-east-1"
        assert adapter.table == mock_table

    @patch("guard.adapters.dynamodb_adapter.boto3")
    def test_init_with_custom_region(self, mock_boto3: MagicMock) -> None:
        """Test initialization with custom region."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table", region="eu-west-1")

        mock_boto3.resource.assert_called_once_with("dynamodb", region_name="eu-west-1")
        assert adapter.region == "eu-west-1"

    @patch("guard.adapters.dynamodb_adapter.boto3")
    def test_init_failure_raises_state_store_error(self, mock_boto3: MagicMock) -> None:
        """Test initialization failure raises StateStoreError."""
        error_response = {"Error": {"Code": "ResourceNotFoundException"}}
        mock_boto3.resource.side_effect = ClientError(error_response, "DescribeTable")

        with pytest.raises(StateStoreError) as exc_info:
            DynamoDBAdapter(table_name="nonexistent-table")

        assert "Failed to initialize DynamoDB adapter" in str(exc_info.value)


class TestDynamoDBAdapterSaveCluster:
    """Tests for save_cluster method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_save_cluster_success(
        self, mock_boto3: MagicMock, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test successful cluster save."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.save_cluster(sample_cluster_config)

        assert result is True
        mock_table.put_item.assert_called_once()

        # Verify the item dict includes all required fields
        call_args = mock_table.put_item.call_args
        item = call_args[1]["Item"]
        assert item["cluster_id"] == sample_cluster_config.cluster_id
        assert item["batch_id"] == sample_cluster_config.batch_id
        assert "last_updated" in item

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_save_cluster_updates_timestamp(
        self, mock_boto3: MagicMock, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that save_cluster updates the last_updated timestamp."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        original_timestamp = sample_cluster_config.last_updated

        await adapter.save_cluster(sample_cluster_config)

        # Check that timestamp was updated in the saved item
        call_args = mock_table.put_item.call_args
        item = call_args[1]["Item"]
        saved_timestamp = datetime.fromisoformat(item["last_updated"])
        assert saved_timestamp >= original_timestamp

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_save_cluster_failure(
        self, mock_boto3: MagicMock, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test save cluster failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        error_response = {"Error": {"Code": "ProvisionedThroughputExceededException"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.save_cluster(sample_cluster_config)

        assert "Failed to save cluster" in str(exc_info.value)


class TestDynamoDBAdapterGetCluster:
    """Tests for get_cluster method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_get_cluster_success(self, mock_boto3: MagicMock) -> None:
        """Test successful cluster retrieval."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
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
                "status": "pending",
            }
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.get_cluster("test-cluster")

        mock_table.get_item.assert_called_once_with(Key={"cluster_id": "test-cluster"})
        assert result is not None
        assert isinstance(result, ClusterConfig)
        assert result.cluster_id == "test-cluster"
        assert result.batch_id == "test-batch"

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_get_cluster_not_found(self, mock_boto3: MagicMock) -> None:
        """Test get_cluster returns None when cluster not found."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No "Item" key means not found
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.get_cluster("nonexistent-cluster")

        assert result is None

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_get_cluster_failure(self, mock_boto3: MagicMock) -> None:
        """Test get_cluster failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.get_cluster("test-cluster")

        assert "Failed to get cluster" in str(exc_info.value)


class TestDynamoDBAdapterListClusters:
    """Tests for list_clusters method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_list_clusters_all(self, mock_boto3: MagicMock) -> None:
        """Test listing all clusters (no filters)."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {
                    "cluster_id": "cluster-1",
                    "batch_id": "batch-1",
                    "environment": "test",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "pending",
                },
                {
                    "cluster_id": "cluster-2",
                    "batch_id": "batch-2",
                    "environment": "prod",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "healthy",
                },
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.list_clusters()

        mock_table.scan.assert_called_once()
        assert len(result) == 2
        assert all(isinstance(c, ClusterConfig) for c in result)

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_list_clusters_by_batch(self, mock_boto3: MagicMock) -> None:
        """Test listing clusters filtered by batch_id."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "cluster_id": "cluster-1",
                    "batch_id": "prod-wave-1",
                    "environment": "prod",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "pending",
                }
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.list_clusters(batch_id="prod-wave-1")

        # Should use query with GSI, not scan
        mock_table.query.assert_called_once()
        mock_table.scan.assert_not_called()

        assert len(result) == 1
        assert result[0].batch_id == "prod-wave-1"

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_list_clusters_by_status(self, mock_boto3: MagicMock) -> None:
        """Test listing clusters filtered by status."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {
                    "cluster_id": "cluster-1",
                    "batch_id": "batch-1",
                    "environment": "test",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "healthy",
                },
                {
                    "cluster_id": "cluster-2",
                    "batch_id": "batch-1",
                    "environment": "test",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "pending",
                },
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.list_clusters(status=ClusterStatus.HEALTHY)

        # Should filter in code after scan
        assert len(result) == 1
        assert result[0].status == ClusterStatus.HEALTHY

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_list_clusters_empty(self, mock_boto3: MagicMock) -> None:
        """Test listing clusters when table is empty."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.list_clusters()

        assert result == []

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_list_clusters_failure(self, mock_boto3: MagicMock) -> None:
        """Test list_clusters failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.scan.side_effect = Exception("DynamoDB error")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.list_clusters()

        assert "Failed to list clusters" in str(exc_info.value)


class TestDynamoDBAdapterUpdateClusterStatus:
    """Tests for update_cluster_status method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_update_cluster_status_success(self, mock_boto3: MagicMock) -> None:
        """Test successful cluster status update."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.update_cluster_status(
            cluster_id="test-cluster", status=ClusterStatus.HEALTHY
        )

        assert result is True
        mock_table.update_item.assert_called_once()

        # Verify update expression includes status and timestamp
        call_args = mock_table.update_item.call_args
        assert "status" in call_args[1]["UpdateExpression"]
        assert "last_updated" in call_args[1]["UpdateExpression"]

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_update_cluster_status_with_metadata(self, mock_boto3: MagicMock) -> None:
        """Test cluster status update with additional metadata."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.update_cluster_status(
            cluster_id="test-cluster",
            status=ClusterStatus.HEALTHY,
            metadata={"current_istio_version": "1.20.0", "validation_passed": True},
        )

        assert result is True

        # Verify metadata fields were added to update expression
        call_args = mock_table.update_item.call_args
        update_expr = call_args[1]["UpdateExpression"]
        assert "current_istio_version" in update_expr
        assert "validation_passed" in update_expr

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_update_cluster_status_failure(self, mock_boto3: MagicMock) -> None:
        """Test cluster status update failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        mock_table.update_item.side_effect = ClientError(error_response, "UpdateItem")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.update_cluster_status("test-cluster", ClusterStatus.HEALTHY)

        assert "Failed to update status" in str(exc_info.value)


class TestDynamoDBAdapterDeleteCluster:
    """Tests for delete_cluster method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_delete_cluster_success(self, mock_boto3: MagicMock) -> None:
        """Test successful cluster deletion."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.delete_cluster("test-cluster")

        assert result is True
        mock_table.delete_item.assert_called_once_with(Key={"cluster_id": "test-cluster"})

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_delete_cluster_failure(self, mock_boto3: MagicMock) -> None:
        """Test cluster deletion failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        error_response = {"Error": {"Code": "ResourceNotFoundException"}}
        mock_table.delete_item.side_effect = ClientError(error_response, "DeleteItem")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.delete_cluster("test-cluster")

        assert "Failed to delete cluster" in str(exc_info.value)


class TestDynamoDBAdapterBatchUpdateStatus:
    """Tests for batch_update_status method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_batch_update_status_all_success(self, mock_boto3: MagicMock) -> None:
        """Test successful batch status update for all clusters."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        cluster_ids = ["cluster-1", "cluster-2", "cluster-3"]
        result = await adapter.batch_update_status(cluster_ids, ClusterStatus.UPGRADING)

        assert result == 3
        assert mock_table.update_item.call_count == 3

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_batch_update_status_partial_failure(self, mock_boto3: MagicMock) -> None:
        """Test batch update continues despite individual failures."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()

        # First call succeeds, second fails, third succeeds
        error_response = {"Error": {"Code": "ValidationException"}}
        mock_table.update_item.side_effect = [
            None,  # Success
            ClientError(error_response, "UpdateItem"),  # Failure
            None,  # Success
        ]

        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        cluster_ids = ["cluster-1", "cluster-2", "cluster-3"]
        result = await adapter.batch_update_status(cluster_ids, ClusterStatus.UPGRADING)

        # Should return count of successes (2 out of 3)
        assert result == 2

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_batch_update_status_empty_list(self, mock_boto3: MagicMock) -> None:
        """Test batch update with empty cluster list."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.batch_update_status([], ClusterStatus.UPGRADING)

        assert result == 0
        mock_table.update_item.assert_not_called()


class TestDynamoDBAdapterQueryByBatch:
    """Tests for query_by_batch method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_query_by_batch_success(self, mock_boto3: MagicMock) -> None:
        """Test successful batch query."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "cluster_id": "cluster-1",
                    "batch_id": "prod-wave-1",
                    "environment": "prod",
                    "region": "us-east-1",
                    "gitlab_repo": "infra/test",
                    "flux_config_path": "test/path",
                    "aws_role_arn": "arn:aws:iam::123:role/test",
                    "current_istio_version": "1.19.0",
                    "datadog_tags": {"cluster": "test", "service": "istio-system", "env": "test"},
                    "owner_team": "team",
                    "owner_handle": "@team",
                    "status": "pending",
                }
            ]
        }
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.query_by_batch("prod-wave-1")

        # Verify GSI query was used
        mock_table.query.assert_called_once()
        call_args = mock_table.query.call_args
        assert call_args[1]["IndexName"] == "batch_id-index"

        assert len(result) == 1
        assert result[0].batch_id == "prod-wave-1"

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_query_by_batch_no_results(self, mock_boto3: MagicMock) -> None:
        """Test batch query with no matching clusters."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        result = await adapter.query_by_batch("nonexistent-batch")

        assert result == []

    @pytest.mark.asyncio
    @patch("guard.adapters.dynamodb_adapter.boto3")
    async def test_query_by_batch_failure(self, mock_boto3: MagicMock) -> None:
        """Test batch query failure raises StateStoreError."""
        mock_dynamodb = MagicMock()
        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("Query failed")
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        adapter = DynamoDBAdapter(table_name="test-table")

        with pytest.raises(StateStoreError) as exc_info:
            await adapter.query_by_batch("prod-wave-1")

        assert "Failed to query batch" in str(exc_info.value)
