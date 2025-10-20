# Testing Guide

GUARD is built using **Test-Driven Development (TDD)** principles. This guide covers our testing practices, structure, and guidelines.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Coverage](#test-coverage)
- [Mocking and Fixtures](#mocking-and-fixtures)
- [Integration Testing](#integration-testing)
- [End-to-End Testing](#end-to-end-testing)
- [CI/CD Integration](#cicd-integration)

## Testing Philosophy

We follow TDD practices:

1. **Red**: Write a failing test first
2. **Green**: Write minimal code to make it pass
3. **Refactor**: Improve code while keeping tests green

### Why TDD?

- **Design**: Tests force you to think about interfaces first
- **Confidence**: High test coverage means safe refactoring
- **Documentation**: Tests serve as executable examples
- **Regression Prevention**: Catch bugs early

## Test Structure

```
tests/
├── unit/                          # Fast, isolated unit tests
│   ├── test_cluster_registry.py   # Registry operations
│   ├── test_pre_check_engine.py   # Health checks
│   ├── test_validation_engine.py  # Validation logic
│   ├── test_gitops_manager.py     # GitOps operations
│   ├── test_rollback_engine.py    # Rollback logic
│   ├── test_config.py             # Configuration loading
│   ├── test_flux_config.py        # Flux YAML updates
│   └── test_metrics_comparator.py # Metrics comparison
├── integration/                   # Integration with external services
│   ├── test_aws_integration.py    # AWS SDK integration
│   ├── test_datadog_integration.py # Datadog API
│   ├── test_gitlab_integration.py # GitLab API
│   ├── test_kubernetes_integration.py # k8s client
│   └── test_istioctl_integration.py # istioctl wrapper
├── e2e/                           # Full workflow tests
│   └── test_full_workflow.py      # Complete upgrade simulation
├── fixtures/                      # Shared test data
│   ├── config.yaml                # Test config
│   ├── clusters.json              # Test cluster data
│   └── flux_helmrelease.yaml      # Sample Flux config
└── conftest.py                    # Shared pytest fixtures
```

## Running Tests

### All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with output capture disabled (see print statements)
pytest -s
```

### By Category

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# End-to-end tests only
pytest tests/e2e/
```

### By Marker

```bash
# Skip slow tests
pytest -m "not slow"

# Run only AWS integration tests
pytest -m requires_aws

# Run only Datadog tests
pytest -m requires_datadog
```

### With Coverage

```bash
# Generate coverage report
pytest --cov=guard --cov-report=html

# View coverage report
open htmlcov/index.html

# Fail if coverage below threshold
pytest --cov=guard --cov-fail-under=90
```

### Specific Tests

```bash
# Run specific test file
pytest tests/unit/test_cluster_registry.py

# Run specific test function
pytest tests/unit/test_cluster_registry.py::test_get_clusters_by_batch

# Run tests matching pattern
pytest -k "registry"
```

## Writing Tests

### Test Naming Convention

```python
def test_<method_name>_<scenario>_<expected_result>():
    """Test that <method> <scenario> <result>."""
```

Examples:
```python
def test_get_clusters_by_batch_returns_correct_clusters():
    """Test that get_clusters_by_batch returns only clusters in the batch."""

def test_run_pre_checks_fails_when_cluster_unhealthy():
    """Test that run_pre_checks fails when any cluster is unhealthy."""
```

### Test Structure (AAA Pattern)

```python
def test_example():
    """Test description."""
    # Arrange: Set up test data and mocks
    cluster = Cluster(
        cluster_id="test-cluster",
        batch_id="test-batch",
        ...
    )
    mock_dynamodb = Mock()

    # Act: Execute the code under test
    result = registry.get_cluster("test-cluster")

    # Assert: Verify the results
    assert result.cluster_id == "test-cluster"
    assert result.batch_id == "test-batch"
```

### Unit Test Example

```python
# tests/unit/test_cluster_registry.py
import pytest
from unittest.mock import Mock, patch
from guard.registry.cluster_registry import ClusterRegistry
from guard.core.models import Cluster

def test_get_clusters_by_batch_returns_correct_clusters(mock_dynamodb_table):
    """Test that clusters are correctly filtered by batch_id."""
    # Arrange
    mock_dynamodb_table.query.return_value = {
        "Items": [
            {
                "cluster_id": "cluster-1",
                "batch_id": "prod-wave-1",
                "environment": "production",
                "region": "us-east-1",
                "gitlab_repo": "infra/k8s",
                "flux_config_path": "clusters/prod/cluster-1/istio.yaml",
                "aws_role_arn": "arn:aws:iam::123:role/Access",
                "current_istio_version": "1.19.3",
                "datadog_tags": {"cluster": "cluster-1"},
            },
            {
                "cluster_id": "cluster-2",
                "batch_id": "prod-wave-1",
                "environment": "production",
                "region": "us-east-1",
                "gitlab_repo": "infra/k8s",
                "flux_config_path": "clusters/prod/cluster-2/istio.yaml",
                "aws_role_arn": "arn:aws:iam::123:role/Access",
                "current_istio_version": "1.19.3",
                "datadog_tags": {"cluster": "cluster-2"},
            },
        ]
    }

    registry = ClusterRegistry(table=mock_dynamodb_table)

    # Act
    result = registry.get_clusters_by_batch("prod-wave-1")

    # Assert
    assert len(result) == 2
    assert result[0].cluster_id == "cluster-1"
    assert result[1].cluster_id == "cluster-2"
    assert all(c.batch_id == "prod-wave-1" for c in result)


def test_get_clusters_by_batch_returns_empty_when_no_matches(mock_dynamodb_table):
    """Test that get_clusters_by_batch returns empty list when no clusters match."""
    # Arrange
    mock_dynamodb_table.query.return_value = {"Items": []}
    registry = ClusterRegistry(table=mock_dynamodb_table)

    # Act
    result = registry.get_clusters_by_batch("nonexistent-batch")

    # Assert
    assert len(result) == 0


def test_update_cluster_status_updates_dynamodb(mock_dynamodb_table):
    """Test that update_cluster_status calls DynamoDB update."""
    # Arrange
    registry = ClusterRegistry(table=mock_dynamodb_table)

    # Act
    registry.update_cluster_status("cluster-1", "upgrading")

    # Assert
    mock_dynamodb_table.update_item.assert_called_once()
    call_args = mock_dynamodb_table.update_item.call_args
    assert call_args[1]["Key"]["cluster_id"] == "cluster-1"
```

### Integration Test Example

```python
# tests/integration/test_datadog_integration.py
import pytest
from guard.clients.datadog_client import DatadogClient

@pytest.mark.requires_datadog
@pytest.mark.slow
async def test_query_metrics_returns_valid_data(datadog_client, test_cluster):
    """Test that querying Datadog metrics returns valid data."""
    # Arrange
    query = f"avg:kubernetes.cpu.usage{{cluster_name:{test_cluster.cluster_id}}}"

    # Act
    result = await datadog_client.query_metrics(
        query=query,
        start_time=int(time.time()) - 3600,
        end_time=int(time.time())
    )

    # Assert
    assert result is not None
    assert "series" in result
    assert len(result["series"]) > 0
```

## Test Coverage

### Coverage Goals

- **Overall**: 90%+ coverage
- **Core modules**: 95%+ coverage
- **Unit tests**: Should cover all business logic
- **Integration tests**: Should cover all external service interactions
- **E2E tests**: Should cover complete workflows

### Checking Coverage

```bash
# Generate coverage report
pytest --cov=guard --cov-report=term-missing

# HTML report for detailed view
pytest --cov=guard --cov-report=html
open htmlcov/index.html
```

### Coverage Report Example

```
Name                                      Stmts   Miss  Cover   Missing
-----------------------------------------------------------------------
src/guard/__init__.py                           2      0   100%
src/guard/checks/pre_check_engine.py          145      8    95%   234-241
src/guard/cli/main.py                          89     12    87%   45-52, 78-81
src/guard/core/config.py                      219      5    98%   187-189
src/guard/gitops/manager.py                   178     15    92%   123-128, 245-251
src/guard/registry/cluster_registry.py        134      3    98%   89-91
src/guard/validation/engine.py                156     18    88%   78-82, 156-167
-----------------------------------------------------------------------
TOTAL                                      1456     89    94%
```

## Mocking and Fixtures

### Common Fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock
from guard.core.config import GuardConfig
from guard.core.models import Cluster

@pytest.fixture
def test_config():
    """Provide test configuration."""
    return GuardConfig.from_file("tests/fixtures/config.yaml")


@pytest.fixture
def test_cluster():
    """Provide test cluster."""
    return Cluster(
        cluster_id="test-cluster-1",
        batch_id="test-batch",
        environment="test",
        region="us-east-1",
        gitlab_repo="infra/k8s",
        flux_config_path="clusters/test/cluster-1/istio.yaml",
        aws_role_arn="arn:aws:iam::123456789:role/TestRole",
        current_istio_version="1.19.3",
        datadog_tags={"cluster": "test-cluster-1"},
        owner_team="platform",
        owner_handle="@platform",
        status="healthy"
    )


@pytest.fixture
def mock_dynamodb_table():
    """Provide mocked DynamoDB table."""
    return Mock()


@pytest.fixture
def mock_gitlab_client():
    """Provide mocked GitLab client."""
    mock = Mock()
    mock.create_merge_request.return_value = {"web_url": "https://gitlab.com/mr/123"}
    return mock


@pytest.fixture
def mock_datadog_client():
    """Provide mocked Datadog client."""
    mock = Mock()
    mock.query_metrics.return_value = {"series": [{"pointlist": [[1234, 0.5]]}]}
    return mock
```

### Using Fixtures

```python
def test_with_fixtures(test_config, test_cluster, mock_gitlab_client):
    """Example test using fixtures."""
    manager = GitOpsManager(config=test_config, gitlab_client=mock_gitlab_client)
    result = manager.create_upgrade_mr([test_cluster], "1.20.0")
    assert result is not None
```

### Async Fixtures

```python
@pytest.fixture
async def async_datadog_client():
    """Provide async Datadog client for integration tests."""
    client = DatadogClient(api_key="test", app_key="test")
    yield client
    await client.close()
```

## Integration Testing

### Prerequisites

Integration tests require access to external services:

```bash
# Set environment variables
export AWS_PROFILE=guard-test
export DATADOG_API_KEY=xxx
export DATADOG_APP_KEY=xxx
export GITLAB_TOKEN=xxx

# Or use .env file
cp .env.example .env
# Edit .env with your credentials
```

### Markers

```python
# tests/integration/test_aws_integration.py
import pytest

@pytest.mark.requires_aws
@pytest.mark.slow
async def test_assume_role():
    """Test AWS STS AssumeRole."""
    # Test code
```

### Running Integration Tests

```bash
# Skip integration tests (default for local development)
pytest -m "not requires_aws and not requires_datadog"

# Run only AWS integration tests
pytest -m requires_aws

# Run all integration tests
pytest tests/integration/
```

## End-to-End Testing

### E2E Test Structure

```python
# tests/e2e/test_full_workflow.py
import pytest
from guard.cli.main import main

@pytest.mark.e2e
@pytest.mark.slow
async def test_complete_upgrade_workflow(test_env):
    """Test complete upgrade workflow from start to finish."""
    # Setup: Create test cluster in test environment
    cluster_id = test_env.create_cluster()

    # Phase 1: Run pre-checks
    result = await main(["run", "--batch", "test", "--target-version", "1.20.0"])
    assert result.exit_code == 0

    # Phase 2: Simulate MR merge
    test_env.merge_mr()

    # Phase 3: Monitor and validate
    result = await main(["monitor", "--batch", "test"])
    assert result.exit_code == 0

    # Verify final state
    cluster = test_env.get_cluster(cluster_id)
    assert cluster.current_istio_version == "1.20.0"
    assert cluster.status == "healthy"
```

### E2E Test Environment

E2E tests use a separate test environment:

- Dedicated test AWS account
- Test EKS cluster
- Test GitLab project
- Test Datadog account

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run unit tests
        run: poetry run pytest tests/unit/ --cov=guard --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run integration tests
        run: poetry run pytest tests/integration/ -m "not slow"
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          DATADOG_API_KEY: ${{ secrets.DATADOG_API_KEY }}
          DATADOG_APP_KEY: ${{ secrets.DATADOG_APP_KEY }}
```

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-unit
        name: pytest-unit
        entry: poetry run pytest tests/unit/
        language: system
        pass_filenames: false
        always_run: true
```

## Best Practices

### DO:

- ✅ Write tests before code (TDD)
- ✅ Use descriptive test names
- ✅ Follow AAA pattern (Arrange, Act, Assert)
- ✅ Mock external dependencies
- ✅ Test edge cases and error conditions
- ✅ Keep tests independent and isolated
- ✅ Use fixtures for common setup
- ✅ Aim for fast unit tests (<100ms each)
- ✅ Group related tests in classes
- ✅ Use parametrize for similar test cases

### DON'T:

- ❌ Skip writing tests
- ❌ Test implementation details
- ❌ Share state between tests
- ❌ Use production credentials in tests
- ❌ Make external API calls in unit tests
- ❌ Write flaky tests
- ❌ Leave commented-out test code
- ❌ Test external libraries

### Parametrized Tests

```python
@pytest.mark.parametrize("version,expected", [
    ("1.19.0", True),
    ("1.20.0", True),
    ("1.18.0", False),  # Too old
    ("2.0.0", False),   # Not supported yet
])
def test_is_supported_version(version, expected):
    """Test version support check."""
    result = is_supported_version(version)
    assert result == expected
```

### Test Classes

```python
class TestClusterRegistry:
    """Tests for ClusterRegistry."""

    def test_get_cluster_returns_cluster(self, mock_dynamodb_table):
        """Test that get_cluster returns the correct cluster."""
        # Test code

    def test_get_cluster_raises_when_not_found(self, mock_dynamodb_table):
        """Test that get_cluster raises exception when cluster not found."""
        # Test code
```

## Troubleshooting

### Common Issues

**Issue**: Tests fail with "ModuleNotFoundError"
```bash
# Solution: Install package in editable mode
pip install -e .
```

**Issue**: Integration tests fail with auth errors
```bash
# Solution: Check credentials
aws sts get-caller-identity
export DATADOG_API_KEY=xxx
```

**Issue**: Async tests not running
```bash
# Solution: Install pytest-asyncio
pip install pytest-asyncio
```

**Issue**: Coverage not including all files
```bash
# Solution: Ensure package is installed
pip install -e .
pytest --cov=guard --cov-report=term-missing
```

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py](https://coverage.readthedocs.io/)
