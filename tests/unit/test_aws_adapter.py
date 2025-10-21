"""Unit tests for AWSAdapter.

Tests the AWS adapter implementation of CloudProvider interface.
All AWS SDK calls are mocked to ensure tests are isolated and fast.
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from guard.adapters.aws_adapter import AWSAdapter
from guard.interfaces.cloud_types import CloudCredentials, ClusterInfo, ClusterToken
from guard.interfaces.exceptions import CloudProviderError


class TestAWSAdapterInit:
    """Tests for AWSAdapter initialization."""

    @patch("guard.adapters.aws_adapter.AWSClient")
    def test_init_with_defaults(self, mock_aws_client_class: MagicMock) -> None:
        """Test initializing adapter with default parameters."""
        mock_client = MagicMock()
        MagicMock()
        mock_secrets_client = MagicMock()
        mock_client.session.client.return_value = mock_secrets_client
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        mock_aws_client_class.assert_called_once_with(region="us-east-1", profile=None)
        assert adapter.client == mock_client
        assert adapter._secrets_client == mock_secrets_client

    @patch("guard.adapters.aws_adapter.AWSClient")
    def test_init_with_custom_region_and_profile(self, mock_aws_client_class: MagicMock) -> None:
        """Test initializing adapter with custom region and profile."""
        mock_client = MagicMock()
        MagicMock()
        mock_secrets_client = MagicMock()
        mock_client.session.client.return_value = mock_secrets_client
        mock_aws_client_class.return_value = mock_client

        AWSAdapter(region="us-west-2", profile="dev")

        mock_aws_client_class.assert_called_once_with(region="us-west-2", profile="dev")


class TestAWSAdapterAssumeRole:
    """Tests for assume_role method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_assume_role_success(self, mock_aws_client_class: MagicMock) -> None:
        """Test successful role assumption."""
        # Setup mocks
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.access_key = "AKIAIOSFODNN7EXAMPLE"
        mock_credentials.secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        mock_credentials.token = "mock-session-token"

        mock_session.get_credentials.return_value = mock_credentials
        mock_client.assume_role.return_value = mock_session
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        # Test assume_role
        result = await adapter.assume_role(
            role_arn="arn:aws:iam::123456789:role/TestRole", session_name="test-session"
        )

        # Verify
        mock_client.assume_role.assert_called_once_with(
            "arn:aws:iam::123456789:role/TestRole", "test-session"
        )
        assert isinstance(result, CloudCredentials)
        assert result.access_key_id == "AKIAIOSFODNN7EXAMPLE"
        assert result.secret_access_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert result.session_token == "mock-session-token"
        assert result.expiration is None

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_assume_role_failure(self, mock_aws_client_class: MagicMock) -> None:
        """Test role assumption failure raises CloudProviderError."""
        mock_client = MagicMock()
        mock_client.assume_role.side_effect = Exception("Access denied")
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.assume_role(
                role_arn="arn:aws:iam::123456789:role/TestRole", session_name="test-session"
            )

        assert "Failed to assume role" in str(exc_info.value)
        assert "Access denied" in str(exc_info.value)


class TestAWSAdapterGetSecret:
    """Tests for get_secret method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_get_secret_success(self, mock_aws_client_class: MagicMock) -> None:
        """Test successful secret retrieval."""
        mock_client = MagicMock()
        mock_secrets_client = MagicMock()
        mock_secrets_client.get_secret_value.return_value = {
            "SecretString": '{"api_key": "test-key", "app_key": "test-app-key"}'
        }
        mock_client.session.client.return_value = mock_secrets_client
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        result = await adapter.get_secret("guard/datadog-credentials")

        mock_secrets_client.get_secret_value.assert_called_once_with(
            SecretId="guard/datadog-credentials"
        )
        assert result["api_key"] == "test-key"
        assert result["app_key"] == "test-app-key"

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_get_secret_not_found(self, mock_aws_client_class: MagicMock) -> None:
        """Test secret not found error."""
        mock_client = MagicMock()
        mock_secrets_client = MagicMock()

        error_response = {"Error": {"Code": "ResourceNotFoundException"}}
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            error_response, "GetSecretValue"
        )
        mock_client.session.client.return_value = mock_secrets_client
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.get_secret("guard/nonexistent-secret")

        assert "Failed to get secret" in str(exc_info.value)
        assert "ResourceNotFoundException" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_get_secret_access_denied(self, mock_aws_client_class: MagicMock) -> None:
        """Test secret access denied error."""
        mock_client = MagicMock()
        mock_secrets_client = MagicMock()

        error_response = {"Error": {"Code": "AccessDeniedException"}}
        mock_secrets_client.get_secret_value.side_effect = ClientError(
            error_response, "GetSecretValue"
        )
        mock_client.session.client.return_value = mock_secrets_client
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.get_secret("guard/protected-secret")

        assert "AccessDeniedException" in str(exc_info.value)


class TestAWSAdapterGetClusterInfo:
    """Tests for get_cluster_info method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_get_cluster_info_success(self, mock_aws_client_class: MagicMock) -> None:
        """Test successful cluster info retrieval."""
        mock_client = MagicMock()
        mock_client.get_eks_cluster_info.return_value = {
            "endpoint": "https://ABC123.eks.us-east-1.amazonaws.com",
            "certificateAuthority": {"data": "LS0tLS1CRUdJTi..."},
            "version": "1.28",
            "status": "ACTIVE",
            "arn": "arn:aws:eks:us-east-1:123456789:cluster/test-cluster",
            "name": "test-cluster",
        }
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        result = await adapter.get_cluster_info("test-cluster")

        mock_client.get_eks_cluster_info.assert_called_once_with("test-cluster")
        assert isinstance(result, ClusterInfo)
        assert result.endpoint == "https://ABC123.eks.us-east-1.amazonaws.com"
        assert result.ca_certificate == "LS0tLS1CRUdJTi..."
        assert result.version == "1.28"
        assert result.status == "ACTIVE"
        assert result.arn == "arn:aws:eks:us-east-1:123456789:cluster/test-cluster"
        assert result.name == "test-cluster"

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_get_cluster_info_not_found(self, mock_aws_client_class: MagicMock) -> None:
        """Test cluster not found error."""
        mock_client = MagicMock()
        mock_client.get_eks_cluster_info.side_effect = Exception("Cluster not found")
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.get_cluster_info("nonexistent-cluster")

        assert "Failed to get cluster info" in str(exc_info.value)


class TestAWSAdapterGenerateClusterToken:
    """Tests for generate_cluster_token method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_generate_cluster_token_success(self, mock_aws_client_class: MagicMock) -> None:
        """Test successful token generation."""
        mock_client = MagicMock()
        mock_client.generate_kubeconfig_token.return_value = {
            "token": "k8s-aws-v1.abc123",
            "endpoint": "https://ABC123.eks.us-east-1.amazonaws.com",
            "ca_data": "LS0tLS1CRUdJTi...",
            "expiration": "2024-01-01T12:00:00Z",
        }
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        result = await adapter.generate_cluster_token("test-cluster")

        mock_client.generate_kubeconfig_token.assert_called_once_with("test-cluster")
        assert isinstance(result, ClusterToken)
        assert result.token == "k8s-aws-v1.abc123"
        assert result.endpoint == "https://ABC123.eks.us-east-1.amazonaws.com"
        assert result.ca_data == "LS0tLS1CRUdJTi..."
        assert result.expiration == "2024-01-01T12:00:00Z"

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_generate_cluster_token_failure(self, mock_aws_client_class: MagicMock) -> None:
        """Test token generation failure."""
        mock_client = MagicMock()
        mock_client.generate_kubeconfig_token.side_effect = Exception("Token generation failed")
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.generate_cluster_token("test-cluster")

        assert "Failed to generate token" in str(exc_info.value)


class TestAWSAdapterListClusters:
    """Tests for list_clusters method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_list_clusters_success(self, mock_aws_client_class: MagicMock) -> None:
        """Test successful cluster listing."""
        mock_client = MagicMock()
        mock_client.list_eks_clusters.return_value = ["cluster-1", "cluster-2", "cluster-3"]
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        result = await adapter.list_clusters()

        mock_client.list_eks_clusters.assert_called_once()
        assert len(result) == 3
        assert "cluster-1" in result
        assert "cluster-2" in result
        assert "cluster-3" in result

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_list_clusters_empty(self, mock_aws_client_class: MagicMock) -> None:
        """Test listing clusters when none exist."""
        mock_client = MagicMock()
        mock_client.list_eks_clusters.return_value = []
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        result = await adapter.list_clusters()

        assert result == []

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_list_clusters_failure(self, mock_aws_client_class: MagicMock) -> None:
        """Test cluster listing failure."""
        mock_client = MagicMock()
        mock_client.list_eks_clusters.side_effect = Exception("API error")
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        with pytest.raises(CloudProviderError) as exc_info:
            await adapter.list_clusters()

        assert "Failed to list clusters" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("guard.adapters.aws_adapter.AWSClient")
    async def test_list_clusters_with_region_parameter(
        self, mock_aws_client_class: MagicMock
    ) -> None:
        """Test list_clusters with region parameter (currently ignored by implementation)."""
        mock_client = MagicMock()
        mock_client.list_eks_clusters.return_value = ["cluster-1"]
        mock_client.session.client.return_value = MagicMock()
        mock_aws_client_class.return_value = mock_client

        adapter = AWSAdapter()

        # Region parameter is accepted but currently not used by underlying client
        result = await adapter.list_clusters(region="us-west-2")

        mock_client.list_eks_clusters.assert_called_once()
        assert len(result) == 1
