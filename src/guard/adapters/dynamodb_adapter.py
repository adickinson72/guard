"""DynamoDB adapter implementing StateStore interface."""

from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from guard.core.models import ClusterConfig, ClusterStatus
from guard.interfaces.exceptions import StateStoreError
from guard.interfaces.state_store import StateStore
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class DynamoDBAdapter(StateStore):
    """Adapter for DynamoDB implementing StateStore interface.

    This adapter wraps boto3 DynamoDB operations, providing a clean
    interface for cluster state persistence.
    """

    def __init__(self, table_name: str, region: str = "us-east-1"):
        """Initialize DynamoDB adapter.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        try:
            self.table_name = table_name
            self.region = region

            dynamodb = boto3.resource("dynamodb", region_name=region)
            self.table = dynamodb.Table(table_name)

            logger.debug("dynamodb_adapter_initialized", table_name=table_name)

        except ClientError as e:
            logger.error("dynamodb_adapter_init_failed", table_name=table_name, error=str(e))
            raise StateStoreError(f"Failed to initialize DynamoDB adapter: {e}") from e

    async def save_cluster(self, cluster: ClusterConfig) -> bool:
        """Save or update a cluster configuration.

        Args:
            cluster: Cluster configuration to save

        Returns:
            True if successful

        Raises:
            StateStoreError: If save fails
        """
        try:
            logger.debug("saving_cluster", cluster_id=cluster.cluster_id)

            # Convert ClusterConfig to dict for DynamoDB
            item = cluster.model_dump()

            # Update last_updated timestamp
            from datetime import datetime

            item["last_updated"] = datetime.utcnow().isoformat()

            self.table.put_item(Item=item)

            logger.info("cluster_saved", cluster_id=cluster.cluster_id)
            return True

        except ClientError as e:
            logger.error(
                "save_cluster_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )
            raise StateStoreError(f"Failed to save cluster {cluster.cluster_id}: {e}") from e

    async def get_cluster(self, cluster_id: str) -> ClusterConfig | None:
        """Get a cluster configuration by ID.

        Args:
            cluster_id: Cluster identifier

        Returns:
            ClusterConfig if found, None otherwise

        Raises:
            StateStoreError: If retrieval fails
        """
        try:
            logger.debug("getting_cluster", cluster_id=cluster_id)

            response = self.table.get_item(Key={"cluster_id": cluster_id})

            if "Item" not in response:
                logger.info("cluster_not_found", cluster_id=cluster_id)
                return None

            # Convert DynamoDB item to ClusterConfig
            cluster = ClusterConfig(**response["Item"])

            logger.info("cluster_retrieved", cluster_id=cluster_id)
            return cluster

        except Exception as e:
            logger.error("get_cluster_failed", cluster_id=cluster_id, error=str(e))
            raise StateStoreError(f"Failed to get cluster {cluster_id}: {e}") from e

    async def list_clusters(
        self,
        batch_id: str | None = None,
        status: ClusterStatus | None = None,
    ) -> list[ClusterConfig]:
        """List clusters with optional filtering.

        Args:
            batch_id: Optional batch ID filter
            status: Optional status filter

        Returns:
            List of matching cluster configurations

        Raises:
            StateStoreError: If listing fails
        """
        try:
            logger.debug("listing_clusters", batch_id=batch_id, status=status)

            if batch_id:
                # Query using GSI on batch_id
                response = self.table.query(
                    IndexName="batch_id-index",
                    KeyConditionExpression=Key("batch_id").eq(batch_id),
                )
            else:
                # Scan entire table
                response = self.table.scan()

            items = response.get("Items", [])

            # Convert to ClusterConfig objects
            clusters = [ClusterConfig(**item) for item in items]

            # Filter by status if specified
            if status:
                clusters = [c for c in clusters if c.status == status]

            logger.info("clusters_listed", count=len(clusters))
            return clusters

        except Exception as e:
            logger.error("list_clusters_failed", error=str(e))
            raise StateStoreError(f"Failed to list clusters: {e}") from e

    async def update_cluster_status(
        self,
        cluster_id: str,
        status: ClusterStatus,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update cluster status.

        Args:
            cluster_id: Cluster identifier
            status: New status
            metadata: Optional additional metadata to update

        Returns:
            True if successful

        Raises:
            StateStoreError: If update fails
        """
        try:
            logger.debug("updating_cluster_status", cluster_id=cluster_id, status=status)

            from datetime import datetime

            update_expression = "SET #status = :status, last_updated = :timestamp"
            expression_values = {
                ":status": status.value if isinstance(status, ClusterStatus) else status,
                ":timestamp": datetime.utcnow().isoformat(),
            }
            expression_names = {"#status": "status"}

            # Add metadata updates if provided
            if metadata:
                for key, value in metadata.items():
                    update_expression += f", {key} = :{key}"
                    expression_values[f":{key}"] = value

            self.table.update_item(
                Key={"cluster_id": cluster_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ExpressionAttributeNames=expression_names,
            )

            logger.info("cluster_status_updated", cluster_id=cluster_id, status=status)
            return True

        except ClientError as e:
            logger.error(
                "update_cluster_status_failed",
                cluster_id=cluster_id,
                error=str(e),
            )
            raise StateStoreError(f"Failed to update status for {cluster_id}: {e}") from e

    async def delete_cluster(self, cluster_id: str) -> bool:
        """Delete a cluster configuration.

        Args:
            cluster_id: Cluster identifier

        Returns:
            True if successful

        Raises:
            StateStoreError: If deletion fails
        """
        try:
            logger.debug("deleting_cluster", cluster_id=cluster_id)

            self.table.delete_item(Key={"cluster_id": cluster_id})

            logger.info("cluster_deleted", cluster_id=cluster_id)
            return True

        except ClientError as e:
            logger.error("delete_cluster_failed", cluster_id=cluster_id, error=str(e))
            raise StateStoreError(f"Failed to delete cluster {cluster_id}: {e}") from e

    async def batch_update_status(self, cluster_ids: list[str], status: ClusterStatus) -> int:
        """Update status for multiple clusters.

        Args:
            cluster_ids: List of cluster identifiers
            status: New status for all clusters

        Returns:
            Number of clusters successfully updated

        Raises:
            StateStoreError: If batch update fails
        """
        try:
            logger.debug("batch_updating_status", count=len(cluster_ids), status=status)

            updated_count = 0
            for cluster_id in cluster_ids:
                try:
                    await self.update_cluster_status(cluster_id, status)
                    updated_count += 1
                except Exception as e:
                    logger.warning(
                        "batch_update_item_failed",
                        cluster_id=cluster_id,
                        error=str(e),
                    )

            logger.info("batch_status_updated", updated_count=updated_count)
            return updated_count

        except Exception as e:
            logger.error("batch_update_status_failed", error=str(e))
            raise StateStoreError(f"Failed to batch update status: {e}") from e

    async def query_by_batch(self, batch_id: str) -> list[ClusterConfig]:
        """Query all clusters in a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            List of clusters in the batch

        Raises:
            StateStoreError: If query fails
        """
        try:
            logger.debug("querying_by_batch", batch_id=batch_id)

            response = self.table.query(
                IndexName="batch_id-index",
                KeyConditionExpression=Key("batch_id").eq(batch_id),
            )

            items = response.get("Items", [])
            clusters = [ClusterConfig(**item) for item in items]

            logger.info("batch_query_completed", batch_id=batch_id, count=len(clusters))
            return clusters

        except Exception as e:
            logger.error("query_by_batch_failed", batch_id=batch_id, error=str(e))
            raise StateStoreError(f"Failed to query batch {batch_id}: {e}") from e
