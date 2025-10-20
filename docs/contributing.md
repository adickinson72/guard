# Contributing to GUARD

Thank you for your interest in contributing to GUARD (GitOps Upgrade Automation with Rollback Detection)! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please:

- Be respectful and considerate
- Welcome newcomers and help them learn
- Focus on what is best for the community
- Show empathy towards other community members

## Getting Started

### Find an Issue

Look for issues labeled:
- `good first issue` - Great for newcomers
- `help wanted` - We need community help
- `bug` - Bug fixes
- `enhancement` - New features

Or open a new issue to propose a feature or report a bug.

### Discuss First

For significant changes:
1. Open an issue first to discuss the approach
2. Get feedback from maintainers
3. Then start implementing

This saves everyone time and ensures alignment.

## Development Setup

### Prerequisites

- Python 3.11+
- Poetry (package manager)
- Git
- AWS CLI (for integration tests)
- kubectl and istioctl

### Clone and Install

```bash
# Fork the repository on GitHub first
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/guard.git
cd guard

# Add upstream remote
git remote add upstream https://github.com/adickinson72/guard.git

# Install Poetry if needed
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Install pre-commit hooks
poetry run pre-commit install

# Verify setup
poetry run pytest
```

### Development Environment

Create a `.env` file for local development:

```bash
# .env
AWS_PROFILE=guard-dev
AWS_REGION=us-east-1
DATADOG_API_KEY=your-dev-api-key
DATADOG_APP_KEY=your-dev-app-key
GITLAB_TOKEN=your-dev-token
GUARD_LOG_LEVEL=DEBUG
```

## Development Workflow

### 1. Create a Branch

```bash
# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/my-awesome-feature

# Or for bug fixes
git checkout -b fix/issue-123-description
```

### 2. Make Changes

Follow TDD (Test-Driven Development):

```bash
# 1. Write a failing test
# tests/unit/test_my_feature.py
def test_my_new_feature():
    result = my_new_function()
    assert result == expected_value

# 2. Run tests (should fail)
poetry run pytest tests/unit/test_my_feature.py

# 3. Implement the feature
# src/guard/my_module.py

# 4. Run tests (should pass)
poetry run pytest tests/unit/test_my_feature.py

# 5. Refactor while keeping tests green
```

### 3. Follow Code Style

We use:
- **ruff** for linting and formatting
- **mypy** for type checking

```bash
# Format code
poetry run ruff format .

# Run linter
poetry run ruff check .

# Run type checker
poetry run mypy src/

# Fix auto-fixable issues
poetry run ruff check --fix .
```

### 4. Write Tests

All code must have tests:

```python
# tests/unit/test_cluster_registry.py
import pytest
from guard.registry.cluster_registry import ClusterRegistry

def test_get_clusters_by_batch_returns_correct_clusters(mock_dynamodb_table):
    """Test that clusters are correctly filtered by batch_id."""
    # Arrange
    mock_dynamodb_table.query.return_value = {
        "Items": [
            {"cluster_id": "cluster-1", "batch_id": "prod-wave-1", ...},
            {"cluster_id": "cluster-2", "batch_id": "prod-wave-1", ...},
        ]
    }
    registry = ClusterRegistry(table=mock_dynamodb_table)

    # Act
    result = registry.get_clusters_by_batch("prod-wave-1")

    # Assert
    assert len(result) == 2
    assert all(c.batch_id == "prod-wave-1" for c in result)
```

See [Testing Guide](testing.md) for details.

### 5. Run All Checks

Before committing:

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=guard --cov-report=term-missing

# Ensure coverage meets threshold (90%)
poetry run pytest --cov=guard --cov-fail-under=90

# Run linting
poetry run ruff check .

# Run type checking
poetry run mypy src/

# Or run all checks at once
poetry run pre-commit run --all-files
```

## Testing

### Test Requirements

- **Unit tests** for all business logic (90%+ coverage)
- **Integration tests** for external service interactions
- **Type hints** for all functions
- **Docstrings** for public APIs

### Running Tests

```bash
# All tests
poetry run pytest

# Specific category
poetry run pytest tests/unit/
poetry run pytest tests/integration/

# Specific file
poetry run pytest tests/unit/test_cluster_registry.py

# Specific test
poetry run pytest tests/unit/test_cluster_registry.py::test_get_clusters_by_batch

# With coverage
poetry run pytest --cov=guard --cov-report=html
open htmlcov/index.html

# Skip slow tests
poetry run pytest -m "not slow"
```

### Writing Good Tests

```python
# Good test example
def test_update_cluster_status_sets_correct_status(mock_dynamodb_table):
    """Test that update_cluster_status updates the cluster's status field.

    Given: A cluster registry with a cluster
    When: update_cluster_status is called with a new status
    Then: The cluster's status is updated in DynamoDB
    """
    # Arrange
    registry = ClusterRegistry(table=mock_dynamodb_table)
    cluster_id = "test-cluster"
    new_status = "upgrading"

    # Act
    registry.update_cluster_status(cluster_id, new_status)

    # Assert
    mock_dynamodb_table.update_item.assert_called_once()
    call_args = mock_dynamodb_table.update_item.call_args
    assert call_args[1]["Key"]["cluster_id"] == cluster_id
    assert "upgrading" in str(call_args[1]["UpdateExpression"])
```

## Code Style

### Python Style Guide

We follow [PEP 8](https://pep8.org/) with some modifications:

- **Line length**: 100 characters (ruff default)
- **Quotes**: Double quotes for strings
- **Imports**: Sorted with `isort` (via ruff)
- **Type hints**: Required for all functions

### Code Structure

```python
"""Module docstring explaining purpose.

This module handles cluster registry operations including querying,
updating, and managing cluster metadata in DynamoDB.
"""

from typing import Any
import logging

from guard.core.models import Cluster
from guard.core.exceptions import RegistryError


logger = logging.getLogger(__name__)


class ClusterRegistry:
    """Manages cluster metadata in DynamoDB.

    This class provides methods to query and update cluster information
    stored in a DynamoDB table.

    Attributes:
        table: DynamoDB table resource
        table_name: Name of the DynamoDB table
    """

    def __init__(self, table_name: str) -> None:
        """Initialize cluster registry.

        Args:
            table_name: Name of DynamoDB table containing cluster data
        """
        self.table_name = table_name
        # Implementation

    def get_clusters_by_batch(self, batch_id: str) -> list[Cluster]:
        """Get all clusters in a specific batch.

        Args:
            batch_id: ID of the batch to query

        Returns:
            List of Cluster objects in the batch

        Raises:
            RegistryError: If query fails
        """
        logger.info(f"Querying clusters for batch: {batch_id}")
        # Implementation
```

### Type Hints

Always use type hints:

```python
# Good
def get_cluster(cluster_id: str) -> Cluster:
    """Get cluster by ID."""
    pass

def update_status(cluster_id: str, status: str) -> None:
    """Update cluster status."""
    pass

async def run_checks(clusters: list[Cluster]) -> dict[str, bool]:
    """Run health checks on clusters."""
    pass

# Bad (no type hints)
def get_cluster(cluster_id):
    """Get cluster by ID."""
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def create_merge_request(
    self,
    clusters: list[Cluster],
    target_version: str,
    health_report: str
) -> dict[str, Any]:
    """Create GitLab merge request for Istio upgrade.

    Args:
        clusters: List of clusters to upgrade
        target_version: Target Istio version (e.g., "1.20.0")
        health_report: Pre-upgrade health check report

    Returns:
        Dictionary containing MR details:
            - web_url: URL to the merge request
            - iid: MR internal ID
            - title: MR title

    Raises:
        GitLabError: If MR creation fails
        ConfguardrationError: If GitLab config is invalid
    """
    pass
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Test additions or changes
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance tasks

### Examples

```bash
# Feature
git commit -m "feat(validation): add custom Datadog query support

Allow users to define custom Datadog queries in confguardration
for validation checks. Queries support template variables for
cluster name and environment.

Closes #123"

# Bug fix
git commit -m "fix(registry): handle missing cluster gracefully

Return None instead of raising exception when cluster not found
in registry to allow better error handling in calling code.

Fixes #456"

# Documentation
git commit -m "docs(readme): update installation instructions

Add Poetry installation steps and update pip install command."

# Breaking change
git commit -m "feat(config)!: change config file format to YAML

BREAKING CHANGE: Confguardration files must now be in YAML format
instead of JSON. Migration script provided in scripts/migrate-config.py"
```

## Pull Request Process

### 1. Push Your Branch

```bash
# Commit your changes
git add .
git commit -m "feat(validation): add custom metrics support"

# Push to your fork
git push origin feature/my-awesome-feature
```

### 2. Create Pull Request

1. Go to GitHub and create a PR from your fork
2. Fill out the PR template:

```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## How Has This Been Tested?
Describe the tests you ran

## Checklist
- [ ] My code follows the code style of this project
- [ ] I have added tests to cover my changes
- [ ] All new and existing tests pass
- [ ] I have updated the documentation accordingly
- [ ] My changes generate no new warnings
```

### 3. Code Review

Maintainers will review your PR and may request changes:

- Address feedback promptly
- Push new commits to the same branch
- Re-request review when ready

### 4. Merge

Once approved, maintainers will merge your PR.

## Release Process

### Versioning

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Creating a Release

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release tag:

```bash
git tag -a v1.2.0 -m "Release version 1.2.0"
git push upstream v1.2.0
```

4. GitHub Actions will automatically:
   - Run tests
   - Build package
   - Publish to PyPI

## Development Tips

### Debugging

```bash
# Run with debug logging
GUARD_LOG_LEVEL=DEBUG poetry run guard run --batch test --target-version 1.20.0

# Use pdb for debugging
import pdb; pdb.set_trace()

# Use ipdb for better debugging
import ipdb; ipdb.set_trace()
```

### Local Testing

```bash
# Install in editable mode
poetry install

# Test CLI commands
poetry run guard --help
poetry run guard validate --config examples/config.yaml.example
```

### Documentation

Update documentation when adding features:

```bash
# Build docs locally (if using Sphinx)
cd docs
make html
open _build/html/index.html
```

## Getting Help

- **Questions**: Open a [GitHub Discussion](https://github.com/adickinson72/guard/discussions)
- **Bugs**: Open a [GitHub Issue](https://github.com/adickinson72/guard/issues)
- **Chat**: Join #guard-dev on Slack

## Recognition

Contributors are recognized in:
- `CONTRIBUTORS.md` file
- Release notes
- GitHub contributors page

Thank you for contributing to GUARD! 🎉
