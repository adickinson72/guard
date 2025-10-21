"""AWS client for EKS and related operations."""

import base64
from typing import Any, cast

import boto3
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError
from guard.utils.logging import get_logger
from guard.utils.rate_limiter import rate_limited
from guard.utils.retry import retry_on_exception

logger = get_logger(__name__)


class AWSClient:
    """AWS client for STS, EKS operations."""

    def __init__(
        self,
        region: str = "us-east-1",
        profile: str | None = None,
        session: boto3.Session | None = None,
    ):
        """Initialize AWS client.

        Args:
            region: AWS region
            profile: AWS profile name (optional)
            session: Existing boto3 session (optional, overrides profile)
        """
        self.region = region
        self.profile = profile

        # Create session
        if session:
            self.session = session
        elif profile:
            self.session = boto3.Session(profile_name=profile, region_name=region)
        else:
            self.session = boto3.Session(region_name=region)

        # Create clients
        self.sts = self.session.client("sts")
        self.eks = self.session.client("eks")

        logger.debug("aws_client_initialized", region=region, profile=profile)

    @classmethod
    def from_assumed_role(
        cls, role_arn: str, region: str = "us-east-1", session_name: str | None = None
    ) -> "AWSClient":
        """Create AWSClient from an assumed IAM role.

        Args:
            role_arn: IAM role ARN to assume
            region: AWS region
            session_name: Session name (defaults to 'GUARD-Session')

        Returns:
            New AWSClient with assumed role credentials

        Raises:
            AWSError: If role assumption fails
        """
        # Create a temporary client to assume the role
        temp_client = cls(region=region)
        assumed_session = temp_client.assume_role(role_arn, session_name)

        # Create new client with assumed session
        return cls(region=region, session=assumed_session)

    @rate_limited("aws_api")
    @retry_on_exception(exceptions=(ClientError, AWSError), max_attempts=3)
    def assume_role(self, role_arn: str, session_name: str | None = None) -> boto3.Session:
        """Assume an IAM role and return a new session.

        Args:
            role_arn: IAM role ARN to assume
            session_name: Session name (defaults to 'GUARD-Session')

        Returns:
            New boto3 session with assumed role credentials

        Raises:
            AWSError: If role assumption fails
        """
        if not session_name:
            session_name = "GUARD-Session"

        try:
            logger.info("assuming_role", role_arn=role_arn, session_name=session_name)

            response = self.sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600,  # 1 hour
            )

            credentials = response["Credentials"]

            # Create new session with temporary credentials
            assumed_session = boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                region_name=self.region,
            )

            logger.info("role_assumed_successfully", role_arn=role_arn)
            return assumed_session

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error("role_assumption_failed", role_arn=role_arn, error_code=error_code)
            raise AWSError(f"Failed to assume role {role_arn}: {error_code}") from e

    @rate_limited("aws_api")
    @retry_on_exception(exceptions=(ClientError, AWSError), max_attempts=3)
    def get_eks_cluster_info(self, cluster_name: str) -> dict[str, Any]:
        """Get EKS cluster information.

        Args:
            cluster_name: Name of the EKS cluster

        Returns:
            Cluster information dictionary

        Raises:
            AWSError: If cluster info cannot be retrieved
        """
        try:
            logger.debug("getting_eks_cluster_info", cluster_name=cluster_name)

            response = self.eks.describe_cluster(name=cluster_name)
            cluster_info = cast(dict[str, Any], response["cluster"])

            logger.info("eks_cluster_info_retrieved", cluster_name=cluster_name)
            return cluster_info

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(
                "eks_cluster_info_failed",
                cluster_name=cluster_name,
                error_code=error_code,
            )

            if error_code == "ResourceNotFoundException":
                raise AWSError(f"EKS cluster not found: {cluster_name}") from e
            else:
                raise AWSError(
                    f"Failed to get cluster info for {cluster_name}: {error_code}"
                ) from e

    @rate_limited("aws_api")
    @retry_on_exception(exceptions=(ClientError, AWSError), max_attempts=3)
    def generate_kubeconfig_token(self, cluster_name: str) -> dict[str, Any]:
        """Generate a kubeconfig token for EKS cluster.

        Args:
            cluster_name: Name of the EKS cluster

        Returns:
            Dictionary containing token, endpoint, and CA data

        Raises:
            AWSError: If token generation fails
        """
        try:
            logger.debug("generating_kubeconfig_token", cluster_name=cluster_name)

            # Generate a presigned URL for STS GetCallerIdentity
            # This is what `aws eks get-token` does under the hood
            import datetime

            from botocore.model import ServiceId
            from botocore.signers import RequestSigner

            # Get cluster info for endpoint and CA
            cluster_info = self.get_eks_cluster_info(cluster_name)

            # Create a presigned URL for STS GetCallerIdentity
            # with the cluster name as a header
            request_params = {
                "method": "GET",
                "url": f"https://sts.{self.region}.amazonaws.com/",
                "body": {},
                "headers": {
                    "x-k8s-aws-id": cluster_name,
                },
                "context": {},
            }

            # Get credentials from the session
            credentials = self.session.get_credentials()
            if credentials is None:
                raise AWSError(f"Failed to get credentials for cluster {cluster_name}")
            frozen_credentials = credentials.get_frozen_credentials()

            # Create a request signer
            signer = RequestSigner(
                ServiceId("sts"),
                self.region,
                "sts",
                "v4",
                frozen_credentials,
                self.session.events,
            )

            # Generate presigned URL with 60 second expiration
            # This matches the behavior of `aws eks get-token`
            expiration_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=60)

            presigned_url = signer.generate_presigned_url(
                request_params,
                region_name=self.region,
                operation_name="GetCallerIdentity",
                expires_in=60,
            )

            # Encode the URL as base64 and prefix with k8s-aws-v1.
            # This is the EKS authentication token format
            token_bytes = presigned_url.encode("utf-8")
            token_b64 = base64.urlsafe_b64encode(token_bytes).decode("utf-8").rstrip("=")
            token = f"k8s-aws-v1.{token_b64}"

            logger.info("kubeconfig_token_generated", cluster_name=cluster_name)

            return {
                "token": token,
                "endpoint": cluster_info["endpoint"],
                "ca_data": cluster_info["certificateAuthority"]["data"],
                "cluster_name": cluster_name,
                "expiration": expiration_time.isoformat(),
            }

        except Exception as e:
            logger.error(
                "kubeconfig_token_generation_failed", cluster_name=cluster_name, error=str(e)
            )
            raise AWSError(f"Failed to generate kubeconfig token for {cluster_name}: {e}") from e

    @rate_limited("aws_api")
    @retry_on_exception(exceptions=(ClientError,), max_attempts=3)
    def list_eks_clusters(self) -> list[str]:
        """List all EKS clusters in the region.

        Returns:
            List of cluster names

        Raises:
            AWSError: If listing clusters fails
        """
        try:
            logger.debug("listing_eks_clusters", region=self.region)

            response = self.eks.list_clusters()
            clusters = response.get("clusters", [])

            logger.info("eks_clusters_listed", count=len(clusters))
            return clusters

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error("eks_cluster_list_failed", error_code=error_code)
            raise AWSError(f"Failed to list EKS clusters: {error_code}") from e
