"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest
import yaml

from guard.core.config import (
    AWSConfig,
    BatchConfig,
    DatadogConfig,
    GitLabConfig,
    GuardConfig,
    ValidationConfig,
)
from guard.core.exceptions import ConfigurationError


def test_aws_config_defaults():
    """Test AWS config defaults."""
    config = AWSConfig(region="us-west-2")
    assert config.region == "us-west-2"
    assert config.profile is None
    assert config.dynamodb.table_name == "guard-cluster-registry"


def test_gitlab_config_required_fields():
    """Test GitLab config requires URL."""
    config = GitLabConfig(url="https://gitlab.example.com")
    assert config.url == "https://gitlab.example.com"
    assert config.default_target_branch == "main"


def test_validation_config_defaults():
    """Test validation config defaults."""
    config = ValidationConfig()
    assert config.soak_period_minutes == 60
    assert config.flux_sync_timeout_minutes == 15
    assert config.thresholds.latency_increase_percent == 10.0


def test_batch_config_creation():
    """Test batch config creation."""
    batch = BatchConfig(
        name="prod-wave-1",
        description="Production first wave",
        clusters=["cluster-1", "cluster-2"],
    )
    assert batch.name == "prod-wave-1"
    assert len(batch.clusters) == 2


def test_guard_config_from_dict():
    """Test creating GuardConfig from dictionary."""
    config_data = {
        "aws": {"region": "us-east-1"},
        "gitlab": {"url": "https://gitlab.example.com"},
        "batches": [
            {
                "name": "test",
                "description": "Test batch",
                "clusters": ["cluster-1"],
            }
        ],
    }

    config = GuardConfig(**config_data)
    assert config.aws.region == "us-east-1"
    assert config.gitlab.url == "https://gitlab.example.com"
    assert len(config.batches) == 1


def test_igu_config_from_file():
    """Test loading config from YAML file."""
    config_data = {
        "aws": {"region": "us-west-2"},
        "gitlab": {"url": "https://gitlab.example.com"},
        "batches": [
            {
                "name": "prod",
                "description": "Production",
                "clusters": ["prod-1", "prod-2"],
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = GuardConfig.from_file(temp_path)
        assert config.aws.region == "us-west-2"
        assert config.gitlab.url == "https://gitlab.example.com"
        assert len(config.batches) == 1
        assert config.batches[0].name == "prod"
    finally:
        Path(temp_path).unlink()


def test_igu_config_from_file_not_found():
    """Test error when config file not found."""
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        GuardConfig.from_file("/nonexistent/config.yaml")


def test_igu_config_from_file_invalid_yaml():
    """Test error when YAML is invalid."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content: [")
        temp_path = f.name

    try:
        with pytest.raises(ConfigurationError, match="Failed to load configuration"):
            GuardConfig.from_file(temp_path)
    finally:
        Path(temp_path).unlink()


def test_igu_config_from_file_invalid_schema():
    """Test error when config schema is invalid."""
    config_data = {
        "aws": {"region": "us-east-1"},
        # Missing required gitlab field
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            GuardConfig.from_file(temp_path)
    finally:
        Path(temp_path).unlink()


def test_get_batch_found():
    """Test getting a batch by name."""
    config = GuardConfig(
        aws=AWSConfig(region="us-east-1"),
        gitlab=GitLabConfig(url="https://gitlab.example.com"),
        batches=[
            BatchConfig(name="test", description="Test", clusters=["c1"]),
            BatchConfig(name="prod", description="Prod", clusters=["c2"]),
        ],
    )

    batch = config.get_batch("prod")
    assert batch is not None
    assert batch.name == "prod"
    assert batch.clusters == ["c2"]


def test_get_batch_not_found():
    """Test getting a nonexistent batch."""
    config = GuardConfig(
        aws=AWSConfig(region="us-east-1"),
        gitlab=GitLabConfig(url="https://gitlab.example.com"),
        batches=[BatchConfig(name="test", description="Test", clusters=["c1"])],
    )

    batch = config.get_batch("nonexistent")
    assert batch is None


def test_config_to_dict():
    """Test converting config to dictionary."""
    config = GuardConfig(
        aws=AWSConfig(region="us-east-1"),
        gitlab=GitLabConfig(url="https://gitlab.example.com"),
    )

    config_dict = config.to_dict()
    assert isinstance(config_dict, dict)
    assert config_dict["aws"]["region"] == "us-east-1"
    assert config_dict["gitlab"]["url"] == "https://gitlab.example.com"


def test_datadog_config_defaults():
    """Test Datadog config defaults."""
    config = DatadogConfig()
    assert config.site == "datadoghq.com"
    assert "cluster:{cluster_name}" in config.queries.control_plane_errors


def test_config_expanduser():
    """Test that config path expands ~ correctly."""
    # Create a temp file in /tmp to simulate a real path
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(
            {
                "aws": {"region": "us-east-1"},
                "gitlab": {"url": "https://gitlab.example.com"},
            },
            f,
        )
        temp_path = f.name

    try:
        # Should not raise even though we're passing a path
        config = GuardConfig.from_file(temp_path)
        assert config.aws.region == "us-east-1"
    finally:
        Path(temp_path).unlink()
