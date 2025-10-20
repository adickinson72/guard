"""State store interface for persistent state management."""

from abc import ABC, abstractmethod
from typing import Any

from guard.core.models import ClusterConfig, ClusterStatus


class StateStore(ABC):
    """Abstract interface for state persistence.

    This interface abstracts state storage (DynamoDB, Postgres, Redis, etc.)
    providing unified CRUD operations for cluster state.

    Design Philosophy:
    - Hides storage implementation details
    - Works with Pydantic models directly
    - Supports both single-cluster and batch operations
    """

    @abstractmethod
    async def save_cluster(self, cluster: ClusterConfig) -> bool:
        """Save or update a cluster configuration.

        Args:
            cluster: Cluster configuration to save

        Returns:
            True if successful

        Raises:
            StateStoreError: If save fails
        """

    @abstractmethod
    async def get_cluster(self, cluster_id: str) -> ClusterConfig | None:
        """Get a cluster configuration by ID.

        Args:
            cluster_id: Cluster identifier

        Returns:
            ClusterConfig if found, None otherwise

        Raises:
            StateStoreError: If retrieval fails
        """

    @abstractmethod
    async def list_clusters(
        self, batch_id: str | None = None, status: ClusterStatus | None = None
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

    @abstractmethod
    async def update_cluster_status(
        self, cluster_id: str, status: ClusterStatus, metadata: dict[str, Any] | None = None
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

    @abstractmethod
    async def delete_cluster(self, cluster_id: str) -> bool:
        """Delete a cluster configuration.

        Args:
            cluster_id: Cluster identifier

        Returns:
            True if successful

        Raises:
            StateStoreError: If deletion fails
        """

    @abstractmethod
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

    @abstractmethod
    async def query_by_batch(self, batch_id: str) -> list[ClusterConfig]:
        """Query all clusters in a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            List of clusters in the batch

        Raises:
            StateStoreError: If query fails
        """
