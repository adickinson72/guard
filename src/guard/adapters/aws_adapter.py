"""AWS adapter implementing CloudProvider interface."""

from botocore.exceptions import ClientError

from guard.clients.aws_client import AWSClient
from guard.interfaces.cloud_provider import CloudProvider
from guard.interfaces.cloud_types import CloudCredentials, ClusterInfo, ClusterToken
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

    async def assume_role(self, role_arn: str, session_name: str) -> CloudCredentials:
        """Assume an IAM role and return credentials.

        Args:
            role_arn: Role ARN to assume
            session_name: Session name for tracking

        Returns:
            CloudCredentials object

        Raises:
            CloudProviderError: If role assumption fails
        """
        try:
            session = self.client.assume_role(role_arn, session_name)

            # Extract credentials from session
            credentials = session.get_credentials()

            # Handle potential None credentials
            if credentials is None:
                raise CloudProviderError(f"No credentials returned for role {role_arn}")

            # Handle potential None token (though unlikely for assume_role)
            if credentials.token is None:
                raise CloudProviderError(f"No session token returned for role {role_arn}")

            return CloudCredentials(
                access_key_id=credentials.access_key,
                secret_access_key=credentials.secret_key,
                session_token=credentials.token,
                expiration=None,  # boto3 doesn't expose expiration directly
            )
        except CloudProviderError:
            # Re-raise CloudProviderError as-is
            raise
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

    async def get_cluster_info(self, cluster_name: str) -> ClusterInfo:
        """Get cluster information.

        Args:
            cluster_name: Name of the cluster

        Returns:
            ClusterInfo object

        Raises:
            CloudProviderError: If cluster info cannot be retrieved
        """
        try:
            cluster_info = self.client.get_eks_cluster_info(cluster_name)

            # Create ClusterInfo object
            return ClusterInfo(
                endpoint=cluster_info["endpoint"],
                ca_certificate=cluster_info["certificateAuthority"]["data"],
                version=cluster_info.get("version"),
                status=cluster_info.get("status"),
                arn=cluster_info.get("arn"),
                name=cluster_info.get("name"),
            )
        except Exception as e:
            logger.error("get_cluster_info_failed", cluster_name=cluster_name, error=str(e))
            raise CloudProviderError(f"Failed to get cluster info for {cluster_name}: {e}") from e

    async def generate_cluster_token(self, cluster_name: str) -> ClusterToken:
        """Generate authentication token for cluster access.

        Args:
            cluster_name: Name of the cluster

        Returns:
            ClusterToken object with token info

        Raises:
            CloudProviderError: If token generation fails
        """
        try:
            token_info = self.client.generate_kubeconfig_token(cluster_name)

            return ClusterToken(
                token=token_info["token"],
                expiration=token_info.get("expiration"),
                endpoint=token_info["endpoint"],
                ca_data=token_info["ca_data"],
            )
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

    def create_client_for_cluster(
        self, role_arn: str, region: str | None = None, session_name: str | None = None
    ) -> AWSClient:
        """Create an AWS client with assumed role for cluster access.

        Args:
            role_arn: IAM role ARN for the target cluster
            region: AWS region (uses adapter's region if None)
            session_name: Session name (defaults to 'GUARD-Session')

        Returns:
            AWSClient configured with assumed role credentials

        Raises:
            CloudProviderError: If client creation fails
        """
        try:
            target_region = region or self.client.region
            return AWSClient.from_assumed_role(role_arn, target_region, session_name)
        except Exception as e:
            logger.error("create_cluster_client_failed", role_arn=role_arn, error=str(e))
            raise CloudProviderError(f"Failed to create client for role {role_arn}: {e}") from e
