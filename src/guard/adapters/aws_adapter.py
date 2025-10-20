"""AWS adapter implementing CloudProvider interface."""

from typing import Any

import boto3
from botocore.exceptions import ClientError

from guard.clients.aws_client import AWSClient
from guard.interfaces.cloud_provider import CloudProvider
from guard.interfaces.exceptions import CloudProviderError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class AWSAdapter(CloudProvider):
    """Adapter wrapping AWSClient to implement CloudProvider interface.

    This adapter hides AWS-specific implementation details (boto3, ClientError)
    behind the clean CloudProvider interface.
    """

    def __init__(self, region: str = "us-east-1", profile: str | None = None):
        """Initialize AWS adapter.

        Args:
            region: AWS region
            profile: AWS profile name (optional)
        """
        self.client = AWSClient(region=region, profile=profile)
        self._secrets_client = self.client.session.client("secretsmanager")
        logger.debug("aws_adapter_initialized", region=region)

    async def assume_role(self, role_arn: str, session_name: str) -> dict[str, Any]:
        """Assume an IAM role and return credentials.

        Args:
            role_arn: Role ARN to assume
            session_name: Session name for tracking

        Returns:
            Dictionary with credentials

        Raises:
            CloudProviderError: If role assumption fails
        """
        try:
            session = self.client.assume_role(role_arn, session_name)

            # Extract credentials from session
            credentials = session.get_credentials()

            return {
                "access_key_id": credentials.access_key,
                "secret_access_key": credentials.secret_key,
                "session_token": credentials.token,
                "expiration": None,  # boto3 doesn't expose expiration directly
            }
        except Exception as e:
            logger.error("assume_role_failed", role_arn=role_arn, error=str(e))
            raise CloudProviderError(f"Failed to assume role {role_arn}: {e}") from e

    async def get_secret(self, secret_name: str) -> dict[str, str]:
        """Retrieve a secret from secrets manager.

        Args:
            secret_name: Name/ARN of the secret

        Returns:
            Dictionary of secret key-value pairs

        Raises:
            CloudProviderError: If secret retrieval fails
        """
        try:
            logger.debug("getting_secret", secret_name=secret_name)

            response = self._secrets_client.get_secret_value(SecretId=secret_name)

            # Parse secret string (assuming JSON format)
            import json

            secret_dict = json.loads(response["SecretString"])

            logger.info("secret_retrieved", secret_name=secret_name)
            return secret_dict

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error("get_secret_failed", secret_name=secret_name, error_code=error_code)
            raise CloudProviderError(f"Failed to get secret {secret_name}: {error_code}") from e

    async def get_cluster_info(self, cluster_name: str) -> dict[str, Any]:
        """Get cluster information.

        Args:
            cluster_name: Name of the cluster

        Returns:
            Dictionary with cluster info

        Raises:
            CloudProviderError: If cluster info cannot be retrieved
        """
        try:
            cluster_info = self.client.get_eks_cluster_info(cluster_name)

            # Normalize the response
            return {
                "endpoint": cluster_info["endpoint"],
                "ca_certificate": cluster_info["certificateAuthority"]["data"],
                "version": cluster_info.get("version"),
                "status": cluster_info.get("status"),
                "arn": cluster_info.get("arn"),
                "name": cluster_info.get("name"),
            }
        except Exception as e:
            logger.error("get_cluster_info_failed", cluster_name=cluster_name, error=str(e))
            raise CloudProviderError(f"Failed to get cluster info for {cluster_name}: {e}") from e

    async def generate_cluster_token(self, cluster_name: str) -> dict[str, Any]:
        """Generate authentication token for cluster access.

        Args:
            cluster_name: Name of the cluster

        Returns:
            Dictionary with token info (token, endpoint, ca_data, expiration)

        Raises:
            CloudProviderError: If token generation fails
        """
        try:
            token_info = self.client.generate_kubeconfig_token(cluster_name)

            return {
                "token": token_info["token"],
                "expiration": token_info.get("expiration"),
                "endpoint": token_info["endpoint"],
                "ca_data": token_info["ca_data"],
            }
        except Exception as e:
            logger.error("generate_token_failed", cluster_name=cluster_name, error=str(e))
            raise CloudProviderError(f"Failed to generate token for {cluster_name}: {e}") from e

    async def list_clusters(self, region: str | None = None) -> list[str]:
        """List all clusters in a region.

        Args:
            region: Region to query (uses default if None)

        Returns:
            List of cluster names

        Raises:
            CloudProviderError: If listing fails
        """
        try:
            # Note: current client doesn't support custom region parameter
            # Would need enhancement for multi-region support
            clusters = self.client.list_eks_clusters()
            return clusters
        except Exception as e:
            logger.error("list_clusters_failed", region=region, error=str(e))
            raise CloudProviderError(f"Failed to list clusters: {e}") from e
