"""Unit tests for GUARD CLI commands.

This module tests all CLI commands including run, monitor, rollback, list,
and validate. Tests focus on command parsing, option validation, and ensuring
proper orchestrator calls with mocked dependencies.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from guard import __version__
from guard.cli.main import cli
from guard.core.models import CheckResult, ClusterConfig, DatadogTags
from guard.interfaces.validator import ValidationResult


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file for testing."""
    config_content = """
aws:
  region: us-east-1

datadog:
  api_key: test-api-key
  app_key: test-app-key

gitlab:
  url: https://gitlab.example.com
  token: test-token
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def sample_clusters() -> list[ClusterConfig]:
    """Provide sample cluster configurations."""
    return [
        ClusterConfig(
            cluster_id="eks-test-us-east-1",
            batch_id="test-batch",
            environment="test",
            region="us-east-1",
            gitlab_repo="infra/k8s-clusters",
            flux_config_path="clusters/test/istio-helmrelease.yaml",
            aws_role_arn="arn:aws:iam::123456789:role/test",
            current_istio_version="1.19.3",
            target_istio_version="1.20.0",
            datadog_tags=DatadogTags(cluster="eks-test", service="istio", env="test"),
            owner_team="platform",
            owner_handle="@platform",
        ),
        ClusterConfig(
            cluster_id="eks-test-us-west-2",
            batch_id="test-batch",
            environment="test",
            region="us-west-2",
            gitlab_repo="infra/k8s-clusters",
            flux_config_path="clusters/test-west/istio-helmrelease.yaml",
            aws_role_arn="arn:aws:iam::123456789:role/test",
            current_istio_version="1.19.3",
            target_istio_version="1.20.0",
            datadog_tags=DatadogTags(cluster="eks-test-west", service="istio", env="test"),
            owner_team="platform",
            owner_handle="@platform",
        ),
    ]


@pytest.fixture
def mock_guard_context(mock_config_file: Path, sample_clusters: list[ClusterConfig]) -> MagicMock:
    """Create a mock GuardContext for testing."""
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = sample_clusters
    mock_ctx.registry.list_all_clusters.return_value = sample_clusters
    mock_ctx.registry.update_cluster_status = MagicMock()
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()
    mock_ctx.config.gitlab.url = "https://gitlab.com"
    mock_ctx.gitlab_token = "test-token"
    return mock_ctx


# ==============================================================================
# CLI Group Tests
# ==============================================================================


def test_cli_help_displays_guard_description(cli_runner: CliRunner) -> None:
    """Test that the main CLI displays help with GUARD description."""
    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "GUARD" in result.output
    assert "GitOps Upgrade Automation with Rollback Detection" in result.output


def test_cli_version_option(cli_runner: CliRunner) -> None:
    """Test the --version option displays version info."""
    result = cli_runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_help_lists_all_commands(cli_runner: CliRunner) -> None:
    """Test the --help option displays all commands."""
    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "monitor" in result.output
    assert "rollback" in result.output
    assert "list" in result.output
    assert "validate" in result.output


def test_cli_custom_config_path(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that custom config path is passed to commands."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_from_file:
        mock_from_file.return_value = MagicMock(aws=MagicMock(region="us-east-1"))

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.registry.cluster_registry.ClusterRegistry") as mock_registry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.list_all_clusters = MagicMock(return_value=[])
                mock_registry.return_value = mock_registry_instance

                result = cli_runner.invoke(
                    cli,
                    ["--config", str(mock_config_file), "list"],
                )

                assert result.exit_code == 0
                # Verify config was loaded from the custom path
                mock_from_file.assert_called_once_with(str(mock_config_file))


# ==============================================================================
# Run Command Tests
# ==============================================================================


def test_run_command_requires_batch(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that run command requires --batch option."""
    result = cli_runner.invoke(
        cli,
        ["--config", str(mock_config_file), "run", "--target-version", "1.20.0"],
    )

    assert result.exit_code != 0
    assert "Missing option '--batch'" in result.output or "Error" in result.output


def test_run_command_requires_target_version(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that run command requires --target-version option."""
    result = cli_runner.invoke(
        cli,
        ["--config", str(mock_config_file), "run", "--batch", "test"],
    )

    assert result.exit_code != 0
    assert "Missing option '--target-version'" in result.output or "Error" in result.output


def test_run_command_success(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test successful run command execution."""
    mock_check_results = [
        CheckResult(check_name="test_check", passed=True, message="Success", metrics={})
    ]

    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = sample_clusters
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch("guard.checks.check_orchestrator.CheckOrchestrator") as mock_orch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run_checks = AsyncMock(return_value=mock_check_results)
            mock_orch.return_value = mock_orch_instance

            with patch("guard.gitops.gitops_orchestrator.GitOpsOrchestrator") as mock_gitops:
                mock_gitops_instance = MagicMock()
                mock_mr = MagicMock()
                mock_mr.web_url = "https://gitlab.com/mr/123"
                mock_gitops_instance.create_upgrade_mr = AsyncMock(return_value=mock_mr)
                mock_gitops.return_value = mock_gitops_instance

                with patch("guard.services.istio.istio_service.IstioService"):
                    with patch("guard.adapters.k8s_adapter.KubernetesAdapter"):
                        result = cli_runner.invoke(
                            cli,
                            [
                                "--config",
                                str(mock_config_file),
                                "run",
                                "--batch",
                                "test-batch",
                                "--target-version",
                                "1.20.0",
                            ],
                        )

                        assert result.exit_code == 0
                        assert "GUARD Run Command" in result.output
                        assert "test-batch" in result.output
                        assert "1.20.0" in result.output
                        assert "Success: 2" in result.output


def test_run_command_dry_run(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test run command with --dry-run flag."""
    mock_check_results = [
        CheckResult(check_name="test_check", passed=True, message="Success", metrics={})
    ]

    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = sample_clusters
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch("guard.checks.check_orchestrator.CheckOrchestrator") as mock_orch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run_checks = AsyncMock(return_value=mock_check_results)
            mock_orch.return_value = mock_orch_instance

            with patch("guard.services.istio.istio_service.IstioService"):
                with patch("guard.adapters.k8s_adapter.KubernetesAdapter"):
                    result = cli_runner.invoke(
                        cli,
                        [
                            "--config",
                            str(mock_config_file),
                            "run",
                            "--batch",
                            "test-batch",
                            "--target-version",
                            "1.20.0",
                            "--dry-run",
                        ],
                    )

                    assert result.exit_code == 0
                    assert "Dry-run: Skipping MR creation" in result.output


def test_run_command_max_concurrent(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test run command with --max-concurrent option."""
    mock_check_results = [
        CheckResult(check_name="test_check", passed=True, message="Success", metrics={})
    ]

    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = sample_clusters
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch("guard.checks.check_orchestrator.CheckOrchestrator") as mock_orch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run_checks = AsyncMock(return_value=mock_check_results)
            mock_orch.return_value = mock_orch_instance

            with patch("guard.gitops.gitops_orchestrator.GitOpsOrchestrator") as mock_gitops:
                mock_gitops_instance = MagicMock()
                mock_mr = MagicMock()
                mock_mr.web_url = "https://gitlab.com/mr/123"
                mock_gitops_instance.create_upgrade_mr = AsyncMock(return_value=mock_mr)
                mock_gitops.return_value = mock_gitops_instance

                with patch("guard.services.istio.istio_service.IstioService"):
                    with patch("guard.adapters.k8s_adapter.KubernetesAdapter"):
                        result = cli_runner.invoke(
                            cli,
                            [
                                "--config",
                                str(mock_config_file),
                                "run",
                                "--batch",
                                "test-batch",
                                "--target-version",
                                "1.20.0",
                                "--max-concurrent",
                                "10",
                            ],
                        )

                        assert result.exit_code == 0
                        assert "Max Concurrent: 10" in result.output


def test_run_command_no_clusters_found(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test run command when no clusters are found for batch."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.return_value = MagicMock(
            aws=MagicMock(region="us-east-1"),
            datadog=MagicMock(api_key="test", app_key="test"),
            gitlab=MagicMock(url="https://gitlab.com", token="test"),
        )

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.registry.cluster_registry.ClusterRegistry") as mock_registry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.get_clusters_by_batch = MagicMock(return_value=[])
                mock_registry.return_value = mock_registry_instance

                with patch("guard.adapters.aws_adapter.AWSAdapter"):
                    with patch("guard.adapters.datadog_adapter.DatadogAdapter"):
                        with patch("guard.adapters.gitlab_adapter.GitLabAdapter"):
                            result = cli_runner.invoke(
                                cli,
                                [
                                    "--config",
                                    str(mock_config_file),
                                    "run",
                                    "--batch",
                                    "nonexistent-batch",
                                    "--target-version",
                                    "1.20.0",
                                ],
                            )

                            assert result.exit_code == 0
                            assert "No clusters found" in result.output


def test_run_command_pre_check_failure(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test run command when pre-checks fail."""
    mock_check_results = [
        CheckResult(check_name="test_check", passed=False, message="Check failed", metrics={})
    ]

    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = [sample_clusters[0]]
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch("guard.checks.check_orchestrator.CheckOrchestrator") as mock_orch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run_checks = AsyncMock(return_value=mock_check_results)
            mock_orch.return_value = mock_orch_instance

            with patch("guard.services.istio.istio_service.IstioService"):
                with patch("guard.adapters.k8s_adapter.KubernetesAdapter"):
                    result = cli_runner.invoke(
                        cli,
                        [
                            "--config",
                            str(mock_config_file),
                            "run",
                            "--batch",
                            "test-batch",
                            "--target-version",
                            "1.20.0",
                        ],
                    )

                    assert result.exit_code == 0
                    assert "Pre-checks failed" in result.output
                    assert "Failed: 1" in result.output


# ==============================================================================
# Monitor Command Tests
# ==============================================================================


def test_monitor_command_requires_batch(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that monitor command requires --batch option."""
    result = cli_runner.invoke(cli, ["--config", str(mock_config_file), "monitor"])

    assert result.exit_code != 0
    assert "Missing option '--batch'" in result.output or "Error" in result.output


def test_monitor_command_success(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test successful monitor command execution."""
    mock_validation_results = [
        ValidationResult(
            cluster_id="eks-test-us-east-1",
            validator_name="test_validator",
            passed=True,
            violations=[],
            metrics={},
            timestamp=datetime.now(),
        )
    ]

    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = [sample_clusters[0]]
    mock_ctx.registry.update_status = MagicMock()
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch(
            "guard.validation.validation_orchestrator.ValidationOrchestrator"
        ) as mock_val_orch:
            mock_val_instance = MagicMock()
            mock_val_instance.capture_baseline = AsyncMock(return_value={})
            mock_val_instance.capture_current = AsyncMock(return_value={})
            mock_val_instance.validate_upgrade = AsyncMock(return_value=mock_validation_results)
            mock_val_orch.return_value = mock_val_instance

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch("guard.clients.gitlab_client.GitLabClient"):
                    with patch("guard.validation.validator_registry.ValidatorRegistry"):
                        with patch("guard.services.istio.istio_service.IstioService"):
                            with patch("guard.rollback.engine.RollbackEngine"):
                                result = cli_runner.invoke(
                                    cli,
                                    [
                                        "--config",
                                        str(mock_config_file),
                                        "monitor",
                                        "--batch",
                                        "test-batch",
                                    ],
                                )

                                assert result.exit_code == 0
                                assert "GUARD Monitor Command" in result.output
                                assert "test-batch" in result.output
                                assert "All validations passed" in result.output


# ==============================================================================
# Rollback Command Tests
# ==============================================================================


def test_rollback_command_requires_batch(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that rollback command requires --batch option."""
    result = cli_runner.invoke(
        cli, ["--config", str(mock_config_file), "rollback", "--reason", "test"]
    )

    assert result.exit_code != 0
    assert "Missing option '--batch'" in result.output or "Error" in result.output


def test_rollback_command_requires_reason(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that rollback command requires --reason option."""
    result = cli_runner.invoke(
        cli, ["--config", str(mock_config_file), "rollback", "--batch", "test"]
    )

    assert result.exit_code != 0
    assert "Missing option '--reason'" in result.output or "Error" in result.output


def test_rollback_command_success(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test successful rollback command execution."""
    # Create a mock GuardContext
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)
    mock_ctx.registry.get_clusters_by_batch.return_value = [sample_clusters[0]]
    mock_ctx.registry.update_status = MagicMock()
    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()
    mock_ctx.helm_updater = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        with patch("guard.rollback.engine.RollbackEngine") as mock_rollback:
            mock_rollback_instance = MagicMock()
            mock_rollback_instance.create_rollback_mr = AsyncMock(
                return_value="https://gitlab.com/mr/789"
            )
            mock_rollback.return_value = mock_rollback_instance

            with patch("guard.clients.gitlab_client.GitLabClient"):
                result = cli_runner.invoke(
                    cli,
                    [
                        "--config",
                        str(mock_config_file),
                        "rollback",
                        "--batch",
                        "test-batch",
                        "--reason",
                        "Critical bug detected",
                    ],
                )

                assert result.exit_code == 0
                assert "GUARD Rollback Command" in result.output
                assert "test-batch" in result.output
                assert "Critical bug detected" in result.output
                assert "Rollback MR created" in result.output


# ==============================================================================
# List Command Tests
# ==============================================================================


def test_list_command_all_clusters(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test list command without filters."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.return_value = MagicMock(aws=MagicMock(region="us-east-1"))

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.registry.cluster_registry.ClusterRegistry") as mock_registry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.list_all_clusters = MagicMock(return_value=sample_clusters)
                mock_registry.return_value = mock_registry_instance

                result = cli_runner.invoke(
                    cli,
                    ["--config", str(mock_config_file), "list"],
                )

                assert result.exit_code == 0
                assert "GUARD List Command" in result.output
                # Cluster IDs may be truncated in table display
                assert "eks-test" in result.output
                assert "test-batch" in result.output


def test_list_command_filter_by_batch(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test list command with batch filter."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.return_value = MagicMock(aws=MagicMock(region="us-east-1"))

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.registry.cluster_registry.ClusterRegistry") as mock_registry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.get_clusters_by_batch = MagicMock(
                    return_value=sample_clusters
                )
                mock_registry.return_value = mock_registry_instance

                result = cli_runner.invoke(
                    cli,
                    ["--config", str(mock_config_file), "list", "--batch", "test-batch"],
                )

                assert result.exit_code == 0
                assert "Batch Filter: test-batch" in result.output


def test_list_command_json_format(
    cli_runner: CliRunner,
    mock_config_file: Path,
    sample_clusters: list[ClusterConfig],
) -> None:
    """Test list command with JSON output format."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.return_value = MagicMock(aws=MagicMock(region="us-east-1"))

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.registry.cluster_registry.ClusterRegistry") as mock_registry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.list_all_clusters = MagicMock(return_value=sample_clusters)
                mock_registry.return_value = mock_registry_instance

                result = cli_runner.invoke(
                    cli,
                    ["--config", str(mock_config_file), "list", "--format", "json"],
                )

                assert result.exit_code == 0
                # JSON output should contain cluster data
                assert "eks-test-us-east-1" in result.output
                assert "test-batch" in result.output


# ==============================================================================
# Validate Command Tests
# ==============================================================================


def test_validate_command_success(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test successful validate command execution."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.return_value = MagicMock(
            aws=MagicMock(region="us-east-1"),
            datadog=MagicMock(api_key="test", app_key="test"),
            gitlab=MagicMock(url="https://gitlab.com", token="test"),
        )

        with patch("guard.adapters.dynamodb_adapter.DynamoDBAdapter"):
            with patch("guard.adapters.datadog_adapter.DatadogAdapter"):
                with patch("guard.adapters.gitlab_adapter.GitLabAdapter"):
                    with patch("guard.adapters.aws_adapter.AWSAdapter"):
                        result = cli_runner.invoke(
                            cli,
                            ["--config", str(mock_config_file), "validate"],
                        )

                        assert result.exit_code == 0
                        assert "GUARD Validate Command" in result.output
                        assert "Configuration File" in result.output
                        assert "Config file valid" in result.output
                        assert "DynamoDB Connectivity" in result.output
                        assert "Datadog Connectivity" in result.output
                        assert "GitLab Connectivity" in result.output
                        assert "AWS Connectivity" in result.output
                        assert "Validation complete" in result.output


def test_validate_command_invalid_config(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test validate command with invalid config file."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.side_effect = ValueError("Invalid config format")

        result = cli_runner.invoke(
            cli,
            ["--config", str(mock_config_file), "validate"],
        )

        assert result.exit_code == 0
        assert "Config file invalid" in result.output


def test_validate_command_connection_failures(
    cli_runner: CliRunner, mock_config_file: Path
) -> None:
    """Test validate command with service connection failures."""
    # Create a mock GuardContext with a failing registry property
    mock_ctx = MagicMock()
    mock_ctx.config_path = str(mock_config_file)

    # Make registry property raise exception when accessed
    type(mock_ctx).registry = property(
        lambda self: (_ for _ in ()).throw(Exception("Connection failed"))
    )

    mock_ctx.aws_adapter = MagicMock()
    mock_ctx.datadog_adapter = MagicMock()
    mock_ctx.gitlab_adapter = MagicMock()

    with patch("guard.cli.main.GuardContext", return_value=mock_ctx):
        result = cli_runner.invoke(
            cli,
            ["--config", str(mock_config_file), "validate"],
        )

        assert result.exit_code == 0
        assert "DynamoDB connection failed" in result.output


# ==============================================================================
# Error Handling Tests
# ==============================================================================


def test_run_command_handles_exceptions(cli_runner: CliRunner, mock_config_file: Path) -> None:
    """Test that run command handles and logs exceptions."""
    with patch("guard.core.config.GuardConfig.from_file") as mock_config:
        mock_config.side_effect = Exception("Unexpected error")

        result = cli_runner.invoke(
            cli,
            [
                "--config",
                str(mock_config_file),
                "run",
                "--batch",
                "test",
                "--target-version",
                "1.20.0",
            ],
        )

        # Should raise and exit with error
        assert result.exit_code != 0
