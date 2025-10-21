"""Cluster registry for managing cluster configurations in DynamoDB."""

from datetime import datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError, ClusterNotFoundError
from guard.core.models import ClusterConfig, ClusterStatus
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ClusterRegistry:
    """DynamoDB-based cluster registry."""

    def __init__(self, table_name: str, region: str = "us-east-1"):
        """Initialize cluster registry.

        Args:
            table_name: DynamoDB table name
            region: AWS region
        """
        self.table_name = table_name
        self.region = region

        try:
            dynamodb = boto3.resource("dynamodb", region_name=region)
            self.table = dynamodb.Table(table_name)
            self.dynamodb_client = boto3.client("dynamodb", region_name=region)

            logger.debug(
                "cluster_registry_initialized",
                table_name=table_name,
                region=region,
            )

        except ClientError as e:
            logger.error(
                "cluster_registry_init_failed",
                table_name=table_name,
                error=str(e),
            )
            raise AWSError(f"Failed to initialize cluster registry: {e}") from e

    def get_cluster(self, cluster_id: str) -> ClusterConfig:
        """Get cluster configuration by ID.

        Args:
            cluster_id: Cluster identifier

        Returns:
            ClusterConfig object

        Raises:
            ClusterNotFoundError: If cluster not found
            AWSError: If DynamoDB query fails
        """
        try:
            logger.debug("getting_cluster", cluster_id=cluster_id)

            response = self.table.get_item(Key={"cluster_id": cluster_id})

            if "Item" not in response:
                logger.warning("cluster_not_found", cluster_id=cluster_id)
                raise ClusterNotFoundError(f"Cluster not found: {cluster_id}")

            item = response["Item"]

            # Convert DynamoDB item to ClusterConfig
            cluster_config = ClusterConfig(**item)

            logger.info("cluster_retrieved", cluster_id=cluster_id)
            return cluster_config

        except ClusterNotFoundError:
            raise
        except Exception as e:
            logger.error("get_cluster_failed", cluster_id=cluster_id, error=str(e))
            raise AWSError(f"Failed to get cluster {cluster_id}: {e}") from e

    def get_clusters_by_batch(self, batch_id: str) -> list[ClusterConfig]:
        """Get all clusters in a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            List of ClusterConfig objects

        Raises:
            AWSError: If DynamoDB query fails
        """
        try:
            logger.debug("getting_clusters_by_batch", batch_id=batch_id)

            # Query using GSI on batch_id
            response = self.table.query(
                IndexName="batch-index",
                KeyConditionExpression=Key("batch_id").eq(batch_id),
            )

            items = response.get("Items", [])

            # Convert items to ClusterConfig objects
            clusters = [ClusterConfig(**item) for item in items]

            logger.info(
                "clusters_retrieved_by_batch",
                batch_id=batch_id,
                count=len(clusters),
            )

            return clusters

        except Exception as e:
            logger.error(
                "get_clusters_by_batch_failed",
                batch_id=batch_id,
                error=str(e),
            )
            raise AWSError(f"Failed to get clusters for batch {batch_id}: {e}") from e

    def update_cluster_status(self, cluster_id: str, status: ClusterStatus, **kwargs: Any) -> None:
        """Update cluster status.

        Args:
            cluster_id: Cluster identifier
            status: New status
            **kwargs: Additional fields to update

        Raises:
            AWSError: If DynamoDB update fails
        """
        try:
            logger.debug(
                "updating_cluster_status",
                cluster_id=cluster_id,
                status=status,
            )

            # Build update expression
            update_expr = "SET #status = :status, last_updated = :last_updated"
            expr_attr_names = {"#status": "status"}
            expr_attr_values = {
                ":status": status.value if isinstance(status, ClusterStatus) else status,
                ":last_updated": datetime.utcnow().isoformat(),
            }

            # Add any additional fields
            for key, value in kwargs.items():
                update_expr += f", {key} = :{key}"
                expr_attr_values[f":{key}"] = value

            self.table.update_item(
                Key={"cluster_id": cluster_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
            )

            logger.info("cluster_status_updated", cluster_id=cluster_id, status=status)

        except ClientError as e:
            logger.error(
                "update_cluster_status_failed",
                cluster_id=cluster_id,
                error=str(e),
            )
            raise AWSError(f"Failed to update cluster status: {e}") from e

    def update_cluster_status_atomic(
        self, cluster_id: str, expected_status: str, new_status: str, **kwargs: Any
    ) -> bool:
        """Update cluster status with atomic transaction.

        Args:
            cluster_id: Cluster identifier
            expected_status: Expected current status
            new_status: New status to set
            **kwargs: Additional fields to update

        Returns:
            True if update succeeded, False if status didn't match

        Raises:
            AWSError: If DynamoDB operation fails
        """
        try:
            logger.debug(
                "atomic_status_update",
                cluster_id=cluster_id,
                expected=expected_status,
                new=new_status,
            )

            # Build update expression dynamically - use consistent low-level API
            update_parts = [
                "#status = :new_status",
                "last_updated = :timestamp",
                "#version = if_not_exists(#version, :zero) + :one",
            ]
            expr_attr_names = {"#status": "status", "#version": "version"}
            expr_attr_values = {
                ":new_status": {"S": new_status},
                ":expected_status": {"S": expected_status},
                ":timestamp": {"S": datetime.utcnow().isoformat()},
                ":zero": {"N": "0"},
                ":one": {"N": "1"},
            }

            # Add additional fields with proper type marshalling
            for key, value in kwargs.items():
                update_parts.append(f"{key} = :{key}")
                # Handle different types properly with explicit type annotations
                attr_value: dict[str, Any]
                if isinstance(value, bool):
                    attr_value = {"BOOL": value}
                elif isinstance(value, int | float):
                    attr_value = {"N": str(value)}
                elif value is None:
                    attr_value = {"NULL": True}
                else:
                    attr_value = {"S": str(value)}
                expr_attr_values[f":{key}"] = attr_value

            self.dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"cluster_id": {"S": cluster_id}},
                            "UpdateExpression": "SET " + ", ".join(update_parts),
                            "ConditionExpression": "#status = :expected_status",
                            "ExpressionAttributeNames": expr_attr_names,
                            "ExpressionAttributeValues": expr_attr_values,
                        }
                    }
                ]
            )

            logger.info(
                "atomic_status_updated",
                cluster_id=cluster_id,
                new_status=new_status,
            )
            return True

        except self.dynamodb_client.exceptions.TransactionCanceledException:
            logger.warning(
                "atomic_status_update_rejected",
                cluster_id=cluster_id,
                expected=expected_status,
                reason="status_mismatch",
            )
            return False
        except ClientError as e:
            logger.error(
                "atomic_status_update_failed",
                cluster_id=cluster_id,
                error=str(e),
            )
            raise AWSError(f"Failed to update cluster status atomically: {e}") from e

    def validate_batch_prerequisites(
        self, batch_id: str, batch_order: dict[str, list[str]]
    ) -> tuple[bool, str]:
        """Enforce rollout sequencing.

        Args:
            batch_id: Batch to validate
            batch_order: Dictionary mapping batch_id to list of prerequisite batch_ids

        Returns:
            Tuple of (valid, message)

        Raises:
            AWSError: If validation check fails
        """
        try:
            logger.debug("validating_batch_prerequisites", batch_id=batch_id)

            prerequisites = batch_order.get(batch_id, [])

            if not prerequisites:
                logger.info("no_prerequisites", batch_id=batch_id)
                return True, "No prerequisites required"

            for prereq_batch in prerequisites:
                clusters = self.get_clusters_by_batch(prereq_batch)

                if not clusters:
                    logger.warning(
                        "prerequisite_batch_empty",
                        batch_id=batch_id,
                        prereq=prereq_batch,
                    )
                    continue

                for cluster in clusters:
                    if cluster.status not in [
                        ClusterStatus.HEALTHY,
                        "healthy",
                        "completed",
                    ]:
                        message = (
                            f"Prerequisite batch '{prereq_batch}' not completed. "
                            f"Cluster {cluster.cluster_id} status: {cluster.status}"
                        )
                        logger.error(
                            "prerequisite_not_met",
                            batch_id=batch_id,
                            prereq=prereq_batch,
                            cluster=cluster.cluster_id,
                            status=cluster.status,
                        )
                        return False, message

            logger.info("prerequisites_validated", batch_id=batch_id)
            return True, "All prerequisites met"

        except Exception as e:
            logger.error(
                "prerequisite_validation_failed",
                batch_id=batch_id,
                error=str(e),
            )
            raise AWSError(f"Failed to validate prerequisites: {e}") from e

    def put_cluster(self, cluster: ClusterConfig) -> None:
        """Create or update a cluster configuration.

        Args:
            cluster: ClusterConfig object

        Raises:
            AWSError: If DynamoDB put fails
        """
        try:
            logger.debug("putting_cluster", cluster_id=cluster.cluster_id)

            # Convert ClusterConfig to dict
            item = cluster.model_dump()

            # Ensure proper serialization of nested models
            if "datadog_tags" in item and hasattr(item["datadog_tags"], "model_dump"):
                item["datadog_tags"] = item["datadog_tags"].model_dump()

            if "metadata" in item and hasattr(item["metadata"], "model_dump"):
                item["metadata"] = item["metadata"].model_dump()

            self.table.put_item(Item=item)

            logger.info("cluster_saved", cluster_id=cluster.cluster_id)

        except ClientError as e:
            logger.error(
                "put_cluster_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )
            raise AWSError(f"Failed to save cluster: {e}") from e

    def delete_cluster(self, cluster_id: str) -> None:
        """Delete a cluster from the registry.

        Args:
            cluster_id: Cluster identifier

        Raises:
            AWSError: If DynamoDB delete fails
        """
        try:
            logger.debug("deleting_cluster", cluster_id=cluster_id)

            self.table.delete_item(Key={"cluster_id": cluster_id})

            logger.info("cluster_deleted", cluster_id=cluster_id)

        except ClientError as e:
            logger.error(
                "delete_cluster_failed",
                cluster_id=cluster_id,
                error=str(e),
            )
            raise AWSError(f"Failed to delete cluster: {e}") from e

    def list_all_clusters(self) -> list[ClusterConfig]:
        """List all clusters in the registry.

        Returns:
            List of all ClusterConfig objects

        Raises:
            AWSError: If DynamoDB scan fails
        """
        try:
            logger.debug("listing_all_clusters")

            response = self.table.scan()
            items = response.get("Items", [])

            # Handle pagination
            while "LastEvaluatedKey" in response:
                response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
                items.extend(response.get("Items", []))

            clusters = [ClusterConfig(**item) for item in items]

            logger.info("all_clusters_listed", count=len(clusters))
            return clusters

        except Exception as e:
            logger.error("list_all_clusters_failed", error=str(e))
            raise AWSError(f"Failed to list all clusters: {e}") from e
