"""Cloud provider interface for AWS/cloud operations."""

from abc import ABC, abstractmethod
from typing import Any

from guard.interfaces.cloud_types import CloudCredentials, ClusterInfo, ClusterToken


class CloudProvider(ABC):
    """Abstract interface for cloud provider operations.

    This interface abstracts AWS (or other cloud) operations like:
    - Cross-account role assumption
    - Secrets retrieval
    - EKS cluster information
    - Credential generation

    Implementation Note:
    Concrete implementations should hide provider-specific details
    (boto3 exceptions, response formats, etc.) behind this clean interface.
    """

    @abstractmethod
    async def assume_role(self, role_arn: str, session_name: str) -> CloudCredentials:
        """Assume an IAM role and return credentials.

        Args:
            role_arn: Role ARN to assume
            session_name: Session name for tracking

        Returns:
            CloudCredentials with access keys and session token

        Raises:
            CloudProviderError: If role assumption fails
        """

    @abstractmethod
    async def get_secret(self, secret_name: str) -> dict[str, str]:
        """Retrieve a secret from secrets manager.

        Args:
            secret_name: Name/ARN of the secret

        Returns:
            Dictionary of secret key-value pairs

        Raises:
            CloudProviderError: If secret retrieval fails
        """

    @abstractmethod
    async def get_cluster_info(self, cluster_name: str) -> ClusterInfo:
        """Get cluster information.

        Args:
            cluster_name: Name of the cluster

        Returns:
            ClusterInfo with endpoint, CA cert, version, and status

        Raises:
            CloudProviderError: If cluster info cannot be retrieved
        """

    @abstractmethod
    async def generate_cluster_token(self, cluster_name: str) -> ClusterToken:
        """Generate authentication token for cluster access.

        Args:
            cluster_name: Name of the cluster

        Returns:
            ClusterToken with auth token and expiration

        Raises:
            CloudProviderError: If token generation fails
        """

    @abstractmethod
    async def list_clusters(self, region: str | None = None) -> list[str]:
        """List all clusters in a region.

        Args:
            region: Region to query (uses default if None)

        Returns:
            List of cluster names

        Raises:
            CloudProviderError: If listing fails
        """
