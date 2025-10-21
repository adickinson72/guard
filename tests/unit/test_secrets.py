"""Tests for secrets management."""

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError
from guard.utils.secrets import SecretsManager


@pytest.fixture
def secrets_manager():
    """Create SecretsManager instance with mocked client."""
    with patch("boto3.client"):
        sm = SecretsManager(region="us-east-1")
        sm.client = MagicMock()
        yield sm


def test_secrets_manager_initialization():
    """Test SecretsManager initialization."""
    with patch("boto3.client") as mock_boto_client:
        sm = SecretsManager(region="us-west-2")
        mock_boto_client.assert_called_once_with("secretsmanager", region_name="us-west-2")
        assert sm.region == "us-west-2"


def test_get_secret_string(secrets_manager):
    """Test getting a secret stored as string."""
    secrets_manager.client.get_secret_value.return_value = {"SecretString": "my-secret-value"}

    result = secrets_manager.get_secret("test-secret")
    assert result == "my-secret-value"
    secrets_manager.client.get_secret_value.assert_called_once_with(SecretId="test-secret")


def test_get_secret_binary(secrets_manager):
    """Test getting a secret stored as binary."""
    secrets_manager.client.get_secret_value.return_value = {"SecretBinary": b"binary-secret"}

    result = secrets_manager.get_secret("test-secret")
    assert result == "binary-secret"


def test_get_secret_not_found(secrets_manager):
    """Test error when secret not found."""
    error_response = {"Error": {"Code": "ResourceNotFoundException"}}
    secrets_manager.client.get_secret_value.side_effect = ClientError(
        error_response, "GetSecretValue"
    )

    with pytest.raises(AWSError, match="Secret not found"):
        secrets_manager.get_secret("nonexistent-secret")


def test_get_secret_invalid_request(secrets_manager):
    """Test error on invalid request."""
    error_response = {"Error": {"Code": "InvalidRequestException"}}
    secrets_manager.client.get_secret_value.side_effect = ClientError(
        error_response, "GetSecretValue"
    )

    with pytest.raises(AWSError, match="Invalid secret request"):
        secrets_manager.get_secret("invalid-secret")


def test_get_secret_invalid_parameter(secrets_manager):
    """Test error on invalid parameter."""
    error_response = {"Error": {"Code": "InvalidParameterException"}}
    secrets_manager.client.get_secret_value.side_effect = ClientError(
        error_response, "GetSecretValue"
    )

    with pytest.raises(AWSError, match="Invalid secret parameter"):
        secrets_manager.get_secret("bad-param-secret")


def test_get_secret_other_error(secrets_manager):
    """Test handling of other AWS errors."""
    error_response = {"Error": {"Code": "InternalServiceError"}}
    secrets_manager.client.get_secret_value.side_effect = ClientError(
        error_response, "GetSecretValue"
    )

    with pytest.raises(AWSError, match="Failed to retrieve secret.*InternalServiceError"):
        secrets_manager.get_secret("error-secret")


def test_get_secret_json(secrets_manager):
    """Test getting a secret as JSON."""
    json_data = {"api_key": "abc123", "app_key": "def456"}
    secrets_manager.client.get_secret_value.return_value = {"SecretString": json.dumps(json_data)}

    result = secrets_manager.get_secret_json("test-secret")
    assert result == json_data


def test_get_secret_json_invalid_json(secrets_manager):
    """Test error when secret is not valid JSON."""
    secrets_manager.client.get_secret_value.return_value = {"SecretString": "not-valid-json{"}

    with pytest.raises(AWSError, match="Failed to parse secret as JSON"):
        secrets_manager.get_secret_json("test-secret")


def test_put_secret_update_existing(secrets_manager):
    """Test updating an existing secret."""
    secrets_manager.put_secret("test-secret", "new-value")

    secrets_manager.client.put_secret_value.assert_called_once_with(
        SecretId="test-secret", SecretString="new-value"
    )


def test_put_secret_create_new(secrets_manager):
    """Test creating a new secret."""
    error_response = {"Error": {"Code": "ResourceNotFoundException"}}
    secrets_manager.client.put_secret_value.side_effect = ClientError(
        error_response, "PutSecretValue"
    )

    secrets_manager.put_secret("new-secret", "value")

    secrets_manager.client.create_secret.assert_called_once_with(
        Name="new-secret", SecretString="value"
    )


def test_put_secret_error(secrets_manager):
    """Test error when putting secret fails."""
    error_response = {"Error": {"Code": "InternalServiceError"}}
    secrets_manager.client.put_secret_value.side_effect = ClientError(
        error_response, "PutSecretValue"
    )

    with pytest.raises(AWSError, match="Failed to store secret.*InternalServiceError"):
        secrets_manager.put_secret("test-secret", "value")


def test_delete_secret_with_recovery_window(secrets_manager):
    """Test deleting a secret with recovery window."""
    secrets_manager.delete_secret("test-secret", force_delete=False)

    secrets_manager.client.delete_secret.assert_called_once_with(
        SecretId="test-secret", RecoveryWindowInDays=7
    )


def test_delete_secret_force_delete(secrets_manager):
    """Test force deleting a secret."""
    secrets_manager.delete_secret("test-secret", force_delete=True)

    secrets_manager.client.delete_secret.assert_called_once_with(
        SecretId="test-secret", ForceDeleteWithoutRecovery=True
    )


def test_delete_secret_not_found(secrets_manager):
    """Test deleting a secret that doesn't exist (should not raise)."""
    error_response = {"Error": {"Code": "ResourceNotFoundException"}}
    secrets_manager.client.delete_secret.side_effect = ClientError(error_response, "DeleteSecret")

    # Should not raise an exception
    secrets_manager.delete_secret("nonexistent-secret")


def test_delete_secret_error(secrets_manager):
    """Test error when deleting secret fails."""
    error_response = {"Error": {"Code": "InternalServiceError"}}
    secrets_manager.client.delete_secret.side_effect = ClientError(error_response, "DeleteSecret")

    with pytest.raises(AWSError, match="Failed to delete secret.*InternalServiceError"):
        secrets_manager.delete_secret("test-secret")
