"""Integration tests for AWS client."""

import boto3
import pytest

from guard.clients.aws_client import AWSClient
from guard.core.exceptions import AWSError


@pytest.mark.integration
class TestAWSClientIntegration:
    """Integration tests for AWSClient with real AWS services."""

    def test_client_initialization(self, aws_test_region: str, skip_if_no_aws_credentials):
        """Test AWS client initializes with valid credentials."""
        client = AWSClient(region=aws_test_region)

        assert client.region == aws_test_region
        assert client.session is not None
        assert client.sts is not None
        assert client.eks is not None

    def test_get_caller_identity(self, aws_test_region: str, skip_if_no_aws_credentials):
        """Test that we can retrieve caller identity from STS."""
        client = AWSClient(region=aws_test_region)

        # Get caller identity directly using STS client
        identity = client.sts.get_caller_identity()

        assert "UserId" in identity
        assert "Account" in identity
        assert "Arn" in identity

    def test_list_eks_clusters(self, aws_test_region: str, skip_if_no_aws_credentials):
        """Test listing EKS clusters in the region."""
        client = AWSClient(region=aws_test_region)

        clusters = client.list_eks_clusters()

        # Should return a list (may be empty if no clusters in region)
        assert isinstance(clusters, list)

    def test_get_eks_cluster_info_not_found(self, aws_test_region: str, skip_if_no_aws_credentials):
        """Test getting cluster info for non-existent cluster raises error."""
        client = AWSClient(region=aws_test_region)

        with pytest.raises(AWSError) as exc_info:
            client.get_eks_cluster_info("non-existent-cluster-12345")

        assert "not found" in str(exc_info.value).lower()

    def test_assume_role_invalid_arn(self, aws_test_region: str, skip_if_no_aws_credentials):
        """Test assuming role with invalid ARN raises error."""
        client = AWSClient(region=aws_test_region)

        invalid_arn = "arn:aws:iam::000000000000:role/NonExistentRole"

        with pytest.raises(AWSError):
            client.assume_role(invalid_arn)

    @pytest.mark.skipif(
        not boto3.Session().get_credentials(),
        reason="AWS credentials not available",
    )
    def test_assume_role_with_valid_arn(
        self, aws_test_region: str, aws_test_role_arn: str | None, skip_if_no_aws_credentials
    ):
        """Test assuming role with valid ARN (if test role provided)."""
        if not aws_test_role_arn:
            pytest.skip(
                "AWS_TEST_ROLE_ARN not set. Set this to a valid role ARN to test role assumption."
            )

        client = AWSClient(region=aws_test_region)

        # Attempt to assume the test role
        assumed_session = client.assume_role(aws_test_role_arn, "GUARD-IntegrationTest")

        # Verify we got a valid session
        assert assumed_session is not None
        assert isinstance(assumed_session, boto3.Session)

        # Verify the session has credentials
        credentials = assumed_session.get_credentials()
        assert credentials is not None
        assert credentials.access_key is not None
        assert credentials.secret_key is not None
        assert credentials.token is not None

    def test_get_eks_cluster_info_with_real_cluster(
        self, aws_test_region: str, skip_if_no_aws_credentials
    ):
        """Test getting cluster info for a real cluster (if clusters exist in region)."""
        client = AWSClient(region=aws_test_region)

        # List clusters first
        clusters = client.list_eks_clusters()

        if not clusters:
            pytest.skip("No EKS clusters available in test region for integration testing")

        # Get info for the first cluster
        cluster_name = clusters[0]
        cluster_info = client.get_eks_cluster_info(cluster_name)

        # Verify response structure
        assert cluster_info is not None
        assert "name" in cluster_info
        assert "arn" in cluster_info
        assert "status" in cluster_info
        assert "endpoint" in cluster_info
        assert "certificateAuthority" in cluster_info
        assert cluster_info["name"] == cluster_name

    def test_generate_kubeconfig_token_with_real_cluster(
        self, aws_test_region: str, skip_if_no_aws_credentials
    ):
        """Test generating kubeconfig token for a real cluster."""
        client = AWSClient(region=aws_test_region)

        # List clusters first
        clusters = client.list_eks_clusters()

        if not clusters:
            pytest.skip("No EKS clusters available in test region for integration testing")

        # Generate token for the first cluster
        cluster_name = clusters[0]
        token_data = client.generate_kubeconfig_token(cluster_name)

        # Verify response structure
        assert token_data is not None
        assert "token" in token_data
        assert "endpoint" in token_data
        assert "ca_data" in token_data
        assert "cluster_name" in token_data
        assert "expiration" in token_data

        # Verify token format
        assert token_data["token"].startswith("k8s-aws-v1.")
        assert token_data["cluster_name"] == cluster_name

        # Verify endpoint is a URL
        assert token_data["endpoint"].startswith("https://")

        # Verify CA data is base64 encoded
        import base64

        try:
            base64.b64decode(token_data["ca_data"])
        except Exception as e:
            pytest.fail(f"CA data is not valid base64: {e}")


@pytest.mark.integration
class TestAWSClientCrossAccountIntegration:
    """Integration tests for cross-account AWS operations."""

    def test_cross_account_eks_access(
        self,
        aws_test_region: str,
        aws_test_role_arn: str | None,
        skip_if_no_aws_credentials,
    ):
        """Test accessing EKS cluster in another account via role assumption."""
        if not aws_test_role_arn:
            pytest.skip("AWS_TEST_ROLE_ARN not set. Set this to test cross-account access.")

        client = AWSClient(region=aws_test_region)

        # Assume role in target account
        assumed_session = client.assume_role(aws_test_role_arn, "GUARD-CrossAccountTest")

        # Create new EKS client with assumed credentials
        eks_client = assumed_session.client("eks")

        # Try to list clusters (should succeed if role has permissions)
        response = eks_client.list_clusters()
        clusters = response.get("clusters", [])

        # Should succeed (list may be empty)
        assert isinstance(clusters, list)
