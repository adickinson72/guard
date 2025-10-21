"""Integration test fixtures and configuration."""

import os

import boto3
import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from guard.core.models import ClusterConfig, DatadogTags


@pytest.fixture
def aws_test_region() -> str:
    """AWS region for integration tests."""
    return os.getenv("AWS_TEST_REGION", "us-east-1")


@pytest.fixture
def skip_if_no_aws_credentials():
    """Skip test if AWS credentials are not available."""
    try:
        sts = boto3.client("sts")
        sts.get_caller_identity()
    except (NoCredentialsError, ClientError) as e:
        pytest.skip(f"AWS credentials not available: {e}")


@pytest.fixture
def aws_test_role_arn() -> str | None:
    """Test AWS role ARN from environment (optional)."""
    return os.getenv("AWS_TEST_ROLE_ARN")


@pytest.fixture
def gitlab_test_token() -> str | None:
    """Test GitLab token from environment (optional)."""
    return os.getenv("GITLAB_TEST_TOKEN")


@pytest.fixture
def datadog_test_api_key() -> str | None:
    """Test Datadog API key from environment (optional)."""
    return os.getenv("DATADOG_TEST_API_KEY")


@pytest.fixture
def datadog_test_app_key() -> str | None:
    """Test Datadog App key from environment (optional)."""
    return os.getenv("DATADOG_TEST_APP_KEY")


@pytest.fixture
def skip_if_no_gitlab_token(gitlab_test_token: str | None):
    """Skip test if GitLab token is not available."""
    if not gitlab_test_token:
        pytest.skip("GitLab token not available. Set GITLAB_TEST_TOKEN environment variable.")


@pytest.fixture
def skip_if_no_datadog_credentials(
    datadog_test_api_key: str | None, datadog_test_app_key: str | None
):
    """Skip test if Datadog credentials are not available."""
    if not datadog_test_api_key or not datadog_test_app_key:
        pytest.skip(
            "Datadog credentials not available. Set DATADOG_TEST_API_KEY and "
            "DATADOG_TEST_APP_KEY environment variables."
        )


@pytest.fixture
def integration_test_cluster_config() -> ClusterConfig:
    """Cluster configuration for integration testing.

    Uses environment variables to allow testing against real clusters:
    - GUARD_TEST_CLUSTER_ID
    - GUARD_TEST_CLUSTER_REGION
    - GUARD_TEST_CLUSTER_ROLE_ARN
    """
    cluster_id = os.getenv("GUARD_TEST_CLUSTER_ID", "eks-integration-test")
    region = os.getenv("GUARD_TEST_CLUSTER_REGION", "us-east-1")
    role_arn = os.getenv("GUARD_TEST_CLUSTER_ROLE_ARN", "arn:aws:iam::123456789:role/GUARD-Test")

    return ClusterConfig(
        cluster_id=cluster_id,
        batch_id="integration-test",
        environment="test",
        region=region,
        gitlab_repo="infra/k8s-test-clusters",
        flux_config_path="clusters/test/istio-helmrelease.yaml",
        aws_role_arn=role_arn,
        current_istio_version="1.19.3",
        target_istio_version="1.20.0",
        datadog_tags=DatadogTags(cluster=cluster_id, service="istio-system", env="test"),
        owner_team="platform-engineering",
        owner_handle="@platform-team",
    )
