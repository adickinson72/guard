"""Unit tests for AWS client.

This module tests the AWSClient wrapper for boto3 operations including:
- STS role assumption
- EKS cluster information retrieval
- Kubeconfig token generation
- Error handling for AWS API failures
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import boto3
import pytest
from botocore.exceptions import ClientError

from guard.clients.aws_client import AWSClient
from guard.core.exceptions import AWSError


class TestAWSClientInitialization:
    """Tests for AWSClient initialization."""

    def test_aws_client_initialization_default(self) -> None:
        """Test AWSClient initializes with default settings."""
        with patch("boto3.Session") as mock_session:
            client = AWSClient(region="us-west-2")

            assert client.region == "us-west-2"
            assert client.profile is None
            mock_session.assert_called_once_with(region_name="us-west-2")

    def test_aws_client_initialization_with_profile(self) -> None:
        """Test AWSClient initializes with custom profile."""
        with patch("boto3.Session") as mock_session:
            client = AWSClient(region="us-east-1", profile="test-profile")

            assert client.region == "us-east-1"
            assert client.profile == "test-profile"
            mock_session.assert_called_once_with(
                profile_name="test-profile", region_name="us-east-1"
            )

    def test_aws_client_creates_sts_and_eks_clients(self) -> None:
        """Test AWSClient creates STS and EKS service clients."""
        with patch("boto3.Session") as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            client = AWSClient()

            assert client.sts is not None
            assert client.eks is not None
            assert mock_session.client.call_count == 2


class TestAssumeRole:
    """Tests for assume_role method."""

    @pytest.fixture
    def aws_client(self) -> AWSClient:
        """Create AWSClient with mocked boto3 session."""
        with patch("boto3.Session"):
            return AWSClient()

    def test_assume_role_success(self, aws_client: AWSClient) -> None:
        """Test successful role assumption."""
        # Mock STS assume_role response
        aws_client.sts.assume_role = Mock(
            return_value={
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "SessionToken": "FwoGZXIvYXdzEBYaD...",
                    "Expiration": datetime(2024, 1, 1, 12, 0, 0),
                }
            }
        )

        with patch("boto3.Session") as mock_session_class:
            role_arn = "arn:aws:iam::123456789:role/TestRole"
            session = aws_client.assume_role(role_arn)

            # Verify assume_role was called with correct parameters
            aws_client.sts.assume_role.assert_called_once_with(
                RoleArn=role_arn, RoleSessionName="GUARD-Session", DurationSeconds=3600
            )

            # Verify new session was created with temporary credentials
            mock_session_class.assert_called_with(
                aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
                aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                aws_session_token="FwoGZXIvYXdzEBYaD...",
                region_name=aws_client.region,
            )

    def test_assume_role_with_custom_session_name(self, aws_client: AWSClient) -> None:
        """Test role assumption with custom session name."""
        aws_client.sts.assume_role = Mock(
            return_value={
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                    "Expiration": datetime(2024, 1, 1, 12, 0, 0),
                }
            }
        )

        with patch("boto3.Session"):
            role_arn = "arn:aws:iam::123456789:role/TestRole"
            aws_client.assume_role(role_arn, session_name="CustomSession")

            aws_client.sts.assume_role.assert_called_once()
            call_kwargs = aws_client.sts.assume_role.call_args[1]
            assert call_kwargs["RoleSessionName"] == "CustomSession"

    def test_assume_role_access_denied(self, aws_client: AWSClient) -> None:
        """Test role assumption fails with AccessDenied error."""
        error_response = {
            "Error": {
                "Code": "AccessDenied",
                "Message": "User is not authorized to perform: sts:AssumeRole",
            }
        }
        aws_client.sts.assume_role = Mock(
            side_effect=ClientError(error_response, "AssumeRole")
        )

        role_arn = "arn:aws:iam::123456789:role/TestRole"

        with pytest.raises(AWSError) as exc_info:
            aws_client.assume_role(role_arn)

        assert "AccessDenied" in str(exc_info.value)
        assert role_arn in str(exc_info.value)

    def test_assume_role_invalid_role_arn(self, aws_client: AWSClient) -> None:
        """Test role assumption fails with invalid ARN."""
        error_response = {
            "Error": {
                "Code": "InvalidParameterValue",
                "Message": "Invalid role ARN",
            }
        }
        aws_client.sts.assume_role = Mock(
            side_effect=ClientError(error_response, "AssumeRole")
        )

        with pytest.raises(AWSError) as exc_info:
            aws_client.assume_role("invalid-arn")

        assert "InvalidParameterValue" in str(exc_info.value)


class TestGetEKSClusterInfo:
    """Tests for get_eks_cluster_info method."""

    @pytest.fixture
    def aws_client(self) -> AWSClient:
        """Create AWSClient with mocked boto3 session."""
        with patch("boto3.Session"):
            return AWSClient()

    def test_get_eks_cluster_info_success(self, aws_client: AWSClient) -> None:
        """Test successful EKS cluster info retrieval."""
        cluster_info = {
            "name": "test-cluster",
            "arn": "arn:aws:eks:us-east-1:123:cluster/test-cluster",
            "status": "ACTIVE",
            "endpoint": "https://ABC123.gr7.us-east-1.eks.amazonaws.com",
            "version": "1.28",
            "certificateAuthority": {"data": "LS0tLS1CRUd..."},
        }

        aws_client.eks.describe_cluster = Mock(return_value={"cluster": cluster_info})

        result = aws_client.get_eks_cluster_info("test-cluster")

        assert result["name"] == "test-cluster"
        assert result["status"] == "ACTIVE"
        assert result["endpoint"] == "https://ABC123.gr7.us-east-1.eks.amazonaws.com"
        aws_client.eks.describe_cluster.assert_called_once_with(name="test-cluster")

    def test_get_eks_cluster_info_not_found(self, aws_client: AWSClient) -> None:
        """Test EKS cluster info fails with ResourceNotFoundException."""
        error_response = {
            "Error": {
                "Code": "ResourceNotFoundException",
                "Message": "No cluster found for name: nonexistent-cluster",
            }
        }
        aws_client.eks.describe_cluster = Mock(
            side_effect=ClientError(error_response, "DescribeCluster")
        )

        with pytest.raises(AWSError) as exc_info:
            aws_client.get_eks_cluster_info("nonexistent-cluster")

        assert "not found" in str(exc_info.value)
        assert "nonexistent-cluster" in str(exc_info.value)

    def test_get_eks_cluster_info_access_denied(self, aws_client: AWSClient) -> None:
        """Test EKS cluster info fails with access denied."""
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform: eks:DescribeCluster",
            }
        }
        aws_client.eks.describe_cluster = Mock(
            side_effect=ClientError(error_response, "DescribeCluster")
        )

        with pytest.raises(AWSError) as exc_info:
            aws_client.get_eks_cluster_info("test-cluster")

        assert "AccessDeniedException" in str(exc_info.value)


class TestGenerateKubeconfigToken:
    """Tests for generate_kubeconfig_token method."""

    @pytest.fixture
    def aws_client(self) -> AWSClient:
        """Create AWSClient with mocked boto3 session."""
        with patch("boto3.Session"):
            return AWSClient(region="us-east-1")

    def test_generate_kubeconfig_token_success(self, aws_client: AWSClient) -> None:
        """Test successful kubeconfig token generation."""
        cluster_info = {
            "name": "test-cluster",
            "endpoint": "https://ABC123.gr7.us-east-1.eks.amazonaws.com",
            "certificateAuthority": {"data": "LS0tLS1CRUdJT..."},
        }

        aws_client.eks.describe_cluster = Mock(return_value={"cluster": cluster_info})

        # Mock credentials
        mock_credentials = Mock()
        mock_credentials.get_frozen_credentials.return_value = Mock(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            token=None,
        )
        aws_client.session.get_credentials = Mock(return_value=mock_credentials)

        with patch("guard.clients.aws_client.RequestSigner") as mock_signer_class:
            mock_signer = Mock()
            mock_signer.generate_presigned_url.return_value = (
                "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity&..."
            )
            mock_signer_class.return_value = mock_signer

            result = aws_client.generate_kubeconfig_token("test-cluster")

            assert "token" in result
            assert result["token"].startswith("k8s-aws-v1.")
            assert result["endpoint"] == "https://ABC123.gr7.us-east-1.eks.amazonaws.com"
            assert result["ca_data"] == "LS0tLS1CRUdJT..."
            assert result["cluster_name"] == "test-cluster"
            assert "expiration" in result

    def test_generate_kubeconfig_token_cluster_not_found(
        self, aws_client: AWSClient
    ) -> None:
        """Test kubeconfig token generation fails when cluster not found."""
        error_response = {
            "Error": {
                "Code": "ResourceNotFoundException",
                "Message": "No cluster found",
            }
        }
        aws_client.eks.describe_cluster = Mock(
            side_effect=ClientError(error_response, "DescribeCluster")
        )

        with pytest.raises(AWSError) as exc_info:
            aws_client.generate_kubeconfig_token("nonexistent-cluster")

        assert "not found" in str(exc_info.value)

    def test_generate_kubeconfig_token_credentials_error(
        self, aws_client: AWSClient
    ) -> None:
        """Test kubeconfig token generation fails with credentials error."""
        cluster_info = {
            "name": "test-cluster",
            "endpoint": "https://ABC123.gr7.us-east-1.eks.amazonaws.com",
            "certificateAuthority": {"data": "LS0tLS1CRUdJT..."},
        }

        aws_client.eks.describe_cluster = Mock(return_value={"cluster": cluster_info})
        aws_client.session.get_credentials = Mock(side_effect=Exception("No credentials"))

        with pytest.raises(AWSError) as exc_info:
            aws_client.generate_kubeconfig_token("test-cluster")

        assert "Failed to generate kubeconfig token" in str(exc_info.value)


class TestListEKSClusters:
    """Tests for list_eks_clusters method."""

    @pytest.fixture
    def aws_client(self) -> AWSClient:
        """Create AWSClient with mocked boto3 session."""
        with patch("boto3.Session"):
            return AWSClient()

    def test_list_eks_clusters_success(self, aws_client: AWSClient) -> None:
        """Test successful listing of EKS clusters."""
        aws_client.eks.list_clusters = Mock(
            return_value={"clusters": ["cluster-1", "cluster-2", "cluster-3"]}
        )

        result = aws_client.list_eks_clusters()

        assert len(result) == 3
        assert "cluster-1" in result
        assert "cluster-2" in result
        assert "cluster-3" in result
        aws_client.eks.list_clusters.assert_called_once()

    def test_list_eks_clusters_empty(self, aws_client: AWSClient) -> None:
        """Test listing EKS clusters returns empty list."""
        aws_client.eks.list_clusters = Mock(return_value={"clusters": []})

        result = aws_client.list_eks_clusters()

        assert result == []
        assert isinstance(result, list)

    def test_list_eks_clusters_no_clusters_key(self, aws_client: AWSClient) -> None:
        """Test listing EKS clusters handles missing 'clusters' key."""
        aws_client.eks.list_clusters = Mock(return_value={})

        result = aws_client.list_eks_clusters()

        assert result == []

    def test_list_eks_clusters_access_denied(self, aws_client: AWSClient) -> None:
        """Test listing EKS clusters fails with access denied."""
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform: eks:ListClusters",
            }
        }
        aws_client.eks.list_clusters = Mock(
            side_effect=ClientError(error_response, "ListClusters")
        )

        with pytest.raises(AWSError) as exc_info:
            aws_client.list_eks_clusters()

        assert "AccessDeniedException" in str(exc_info.value)
        assert "Failed to list EKS clusters" in str(exc_info.value)


class TestAWSClientRetryBehavior:
    """Tests for retry and rate limiting decorators."""

    @pytest.fixture
    def aws_client(self) -> AWSClient:
        """Create AWSClient with mocked boto3 session."""
        with patch("boto3.Session"):
            return AWSClient()

    def test_assume_role_retries_on_transient_error(self, aws_client: AWSClient) -> None:
        """Test assume_role retries on transient errors."""
        # First two calls fail, third succeeds
        error_response = {
            "Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}
        }

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientError(error_response, "AssumeRole")
            return {
                "Credentials": {
                    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                    "Expiration": datetime(2024, 1, 1, 12, 0, 0),
                }
            }

        aws_client.sts.assume_role = Mock(side_effect=side_effect)

        with patch("boto3.Session"):
            # Should succeed after retries
            session = aws_client.assume_role("arn:aws:iam::123:role/TestRole")
            assert aws_client.sts.assume_role.call_count == 3

    def test_get_eks_cluster_info_retries_exhausted(self, aws_client: AWSClient) -> None:
        """Test get_eks_cluster_info fails after exhausting retries."""
        error_response = {
            "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
        }

        aws_client.eks.describe_cluster = Mock(
            side_effect=ClientError(error_response, "DescribeCluster")
        )

        with pytest.raises(AWSError):
            aws_client.get_eks_cluster_info("test-cluster")

        # Should retry 3 times (initial + 2 retries)
        assert aws_client.eks.describe_cluster.call_count == 3
