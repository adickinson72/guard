"""Pytest configuration and shared fixtures."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from guard.core.models import ClusterConfig, DatadogTags


@pytest.fixture(autouse=True)
def mock_rate_limiters(request):
    """Mock rate limiter for all tests to avoid registration issues."""
    # Skip mocking for tests marked with no_rate_limiter_mock
    if "no_rate_limiter_mock" in request.keywords:
        yield
        return

    # Mock the RateLimiter.acquire method to always succeed
    with patch("guard.utils.rate_limiter.RateLimiter.acquire", return_value=True):
        yield


@pytest.fixture
def sample_cluster_config() -> ClusterConfig:
    """Provide a sample cluster configuration for testing."""
    return ClusterConfig(
        cluster_id="eks-test-us-east-1",
        batch_id="test",
        environment="test",
        region="us-east-1",
        gitlab_repo="infra/k8s-clusters",
        flux_config_path="clusters/test/us-east-1/istio-helmrelease.yaml",
        aws_role_arn="arn:aws:iam::123456789:role/GUARD-EKSAccess-test",
        current_istio_version="1.19.3",
        target_istio_version="1.20.0",
        datadog_tags=DatadogTags(cluster="eks-test-us-east-1", service="istio-system", env="test"),
        owner_team="platform-engineering",
        owner_handle="@platform-team",
    )


@pytest.fixture
def sample_prod_cluster_config() -> ClusterConfig:
    """Provide a sample production cluster configuration for testing."""
    return ClusterConfig(
        cluster_id="eks-prod-us-east-1-api",
        batch_id="prod-wave-1",
        environment="production",
        region="us-east-1",
        gitlab_repo="infra/k8s-clusters",
        flux_config_path="clusters/prod/us-east-1/api/istio-helmrelease.yaml",
        aws_role_arn="arn:aws:iam::123456789:role/GUARD-EKSAccess-prod",
        current_istio_version="1.19.3",
        target_istio_version="1.20.0",
        datadog_tags=DatadogTags(
            cluster="eks-prod-us-east-1-api", service="istio-system", env="production"
        ),
        owner_team="platform-engineering",
        owner_handle="@platform-team",
    )


@pytest.fixture
def mock_dynamodb_table() -> MagicMock:
    """Mock DynamoDB table for testing."""
    table = MagicMock()
    table.table_name = "guard-cluster-registry"
    return table


@pytest.fixture
def mock_aws_session() -> MagicMock:
    """Mock AWS session for testing."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_kubernetes_client() -> MagicMock:
    """Mock Kubernetes client for testing."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_datadog_client() -> MagicMock:
    """Mock Datadog client for testing."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_gitlab_client() -> MagicMock:
    """Mock GitLab client for testing."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_istioctl_wrapper() -> MagicMock:
    """Mock istioctl wrapper for testing."""
    wrapper = MagicMock()
    wrapper.analyze.return_value = (True, "No validation issues found")
    wrapper.version.return_value = {
        "clientVersion": {"version": "1.20.0"},
        "meshVersion": [{"version": "1.20.0"}],
    }
    return wrapper


# ==============================================================================
# Test Data Fixtures
# ==============================================================================


@pytest.fixture
def sample_datadog_metrics() -> dict[str, Any]:
    """Sample Datadog metrics response."""
    return {
        "status": "ok",
        "series": [
            {
                "metric": "istio.pilot.xds.push.errors",
                "points": [[1234567890, 0.0], [1234567895, 0.0]],
            }
        ],
    }


@pytest.fixture
def sample_kubernetes_nodes() -> list[dict[str, Any]]:
    """Sample Kubernetes nodes response."""
    return [
        {
            "metadata": {"name": "node-1"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        },
        {
            "metadata": {"name": "node-2"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        },
    ]


@pytest.fixture
def sample_istio_pods() -> list[dict[str, Any]]:
    """Sample Istio pods response."""
    return [
        {
            "metadata": {"name": "istiod-1234567890-abcde", "namespace": "istio-system"},
            "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "True"}]},
        }
    ]


@pytest.fixture
def sample_gitlab_project() -> dict[str, Any]:
    """Sample GitLab project response."""
    return {
        "id": 123,
        "name": "k8s-clusters",
        "path_with_namespace": "infra/k8s-clusters",
        "default_branch": "main",
    }


@pytest.fixture
def sample_merge_request() -> dict[str, Any]:
    """Sample GitLab merge request response."""
    return {
        "id": 456,
        "iid": 789,
        "title": "Istio upgrade to v1.20.0 for test",
        "state": "opened",
        "web_url": "https://gitlab.com/infra/k8s-clusters/-/merge_requests/789",
        "source_branch": "feature/istio-1.20.0-test",
        "target_branch": "main",
    }


# ==============================================================================
# Pytest Markers
# ==============================================================================


def pytest_configure(config: Any) -> None:
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "no_rate_limiter_mock: Disable rate limiter mocking")
