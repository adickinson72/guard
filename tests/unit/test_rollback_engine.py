"""Unit tests for RollbackEngine.

Tests automated rollback MR creation and GitLab operations for rollback workflows.
"""

from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from guard.core.models import ClusterConfig, ClusterMetadata, DatadogTags
from guard.rollback.engine import RollbackEngine


@pytest.fixture
def sample_cluster():
    """Create a sample cluster configuration."""
    return ClusterConfig(
        cluster_id="eks-prod-us-east-1",
        batch_id="prod-wave-1",
        environment="production",
        region="us-east-1",
        gitlab_repo="devops/k8s-prod",
        flux_config_path="clusters/prod/istio/helmrelease.yaml",
        aws_role_arn="arn:aws:iam::123456789:role/eks-prod",
        current_istio_version="1.20.0",
        datadog_tags=DatadogTags(cluster="eks-prod-us-east-1", env="prod"),
        owner_team="platform",
        owner_handle="platform-team",
        metadata=ClusterMetadata(),
    )


@pytest.fixture
def mock_gitlab_client():
    """Create a mock GitLab client."""
    client = MagicMock()
    client.create_branch = MagicMock()
    client.get_file = MagicMock(
        return_value="""
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: istio-base
spec:
  chart:
    spec:
      version: "1.20.0"
"""
    )
    client.update_file = MagicMock()
    # create_merge_request should return an object with web_url attribute
    mock_mr = MagicMock()
    mock_mr.web_url = "https://gitlab.com/devops/k8s-prod/-/merge_requests/123"
    client.create_merge_request = MagicMock(return_value=mock_mr)
    return client


@pytest.fixture
def mock_config_updater():
    """Create a mock config updater."""
    updater = MagicMock()
    updater.update_version = AsyncMock(return_value=True)
    updater.get_current_version = AsyncMock(return_value="1.20.0")
    return updater


@pytest.fixture
def rollback_engine(mock_gitlab_client, mock_config_updater):
    """Create RollbackEngine instance with mocked dependencies."""
    return RollbackEngine(gitlab_client=mock_gitlab_client, config_updater=mock_config_updater)


class TestRollbackEngineInitialization:
    """Tests for RollbackEngine initialization."""

    def test_init_success(self, mock_gitlab_client, mock_config_updater):
        """Test successful initialization."""
        engine = RollbackEngine(
            gitlab_client=mock_gitlab_client, config_updater=mock_config_updater
        )

        assert engine.gitlab == mock_gitlab_client
        assert engine.updater == mock_config_updater

    def test_init_with_none_client(self, mock_config_updater):
        """Test initialization with None client."""
        engine = RollbackEngine(gitlab_client=None, config_updater=mock_config_updater)

        assert engine.gitlab is None
        assert engine.updater == mock_config_updater


class TestCreateRollbackMR:
    """Tests for create_rollback_mr method."""

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_success(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test successful rollback MR creation."""
        # Mock datetime to have predictable timestamp
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        # Mock IstioHelmUpdater

        mr_url = await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="Post-upgrade validation failed",
        )

        # Verify branch creation
        mock_gitlab_client.create_branch.assert_called_once()
        call_args = mock_gitlab_client.create_branch.call_args
        assert "rollback/istio-prod-wave-1-1.19.0" in call_args[1]["branch_name"]
        assert call_args[1]["ref"] == "main"

        # Verify file retrieval
        mock_gitlab_client.get_file.assert_called_once()

        # Verify version update
        rollback_engine.updater.update_version.assert_called_once()

        # Verify commit
        mock_gitlab_client.update_file.assert_called_once()
        commit_args = mock_gitlab_client.update_file.call_args
        assert "Rollback Istio from 1.20.0 to 1.19.0" in commit_args[1]["commit_message"]
        assert "Post-upgrade validation failed" in commit_args[1]["commit_message"]

        # Verify MR creation
        mock_gitlab_client.create_merge_request.assert_called_once()
        mr_args = mock_gitlab_client.create_merge_request.call_args
        assert "[ROLLBACK]" in mr_args[1]["title"]
        assert mr_args[1]["draft"] is False

        # Verify return value
        assert mr_url == "https://gitlab.com/devops/k8s-prod/-/merge_requests/123"

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_with_failure_metrics(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test rollback MR creation with failure metrics."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        failure_metrics = {
            "error_rate": "15%",
            "latency_p99": "2500ms",
            "failed_requests": 450,
        }

        await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="High error rate detected",
            failure_metrics=failure_metrics,
        )

        # Verify commit message includes metrics
        commit_args = mock_gitlab_client.update_file.call_args
        commit_message = commit_args[1]["commit_message"]
        assert "error_rate: 15%" in commit_message
        assert "latency_p99: 2500ms" in commit_message
        assert "failed_requests: 450" in commit_message

        # Verify MR description includes metrics
        mr_args = mock_gitlab_client.create_merge_request.call_args
        mr_description = mr_args[1]["description"]
        assert "error_rate" in mr_description
        assert "15%" in mr_description

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    async def test_create_rollback_mr_branch_name_format(
        self,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that rollback branch name includes timestamp and batch."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        with patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0"):
            with patch("guard.rollback.engine.Path.unlink"):
                await rollback_engine.create_rollback_mr(
                    cluster=sample_cluster,
                    current_version="1.20.0",
                    previous_version="1.19.0",
                    failure_reason="Test failure",
                )

        call_args = mock_gitlab_client.create_branch.call_args
        branch_name = call_args[1]["branch_name"]

        assert branch_name.startswith("rollback/istio-")
        assert "prod-wave-1" in branch_name
        assert "1.19.0" in branch_name
        assert "20251020-143000" in branch_name

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_title_format(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that rollback MR title has correct format."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="Test failure",
        )

        mr_args = mock_gitlab_client.create_merge_request.call_args
        title = mr_args[1]["title"]

        assert title.startswith("[ROLLBACK]")
        assert "1.20.0" in title
        assert "1.19.0" in title
        assert "prod-wave-1" in title

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_description_format(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that rollback MR description has correct format."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="Validation failed: high error rate",
        )

        mr_args = mock_gitlab_client.create_merge_request.call_args
        description = mr_args[1]["description"]

        assert "Automated Rollback" in description
        assert "prod-wave-1" in description
        assert "eks-prod-us-east-1" in description
        assert "1.20.0" in description
        assert "1.19.0" in description
        assert "Validation failed: high error rate" in description
        assert "emergency rollback" in description.lower()

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    async def test_create_rollback_mr_not_draft(
        self,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that rollback MRs are not created as drafts."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        with patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0"):
            with patch("guard.rollback.engine.Path.unlink"):
                await rollback_engine.create_rollback_mr(
                    cluster=sample_cluster,
                    current_version="1.20.0",
                    previous_version="1.19.0",
                    failure_reason="Test failure",
                )

        mr_args = mock_gitlab_client.create_merge_request.call_args
        assert mr_args[1]["draft"] is False

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_temp_file_cleanup(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that temporary files are cleaned up."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="Test failure",
        )

        # Verify temp file was deleted
        mock_unlink.assert_called_once()


class TestRollbackEngineErrorHandling:
    """Tests for error handling in RollbackEngine."""

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    async def test_create_rollback_mr_branch_creation_failure(
        self,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test handling of branch creation failure."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"
        mock_gitlab_client.create_branch.side_effect = Exception("Branch creation failed")

        with pytest.raises(Exception, match="Branch creation failed"):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    async def test_create_rollback_mr_file_retrieval_failure(
        self,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test handling of file retrieval failure."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"
        mock_gitlab_client.get_file.side_effect = Exception("File not found")

        with pytest.raises(Exception, match="File not found"):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    async def test_create_rollback_mr_version_update_failure(
        self,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test handling of version update failure."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        rollback_engine.updater.update_version = AsyncMock(side_effect=Exception("Update failed"))

        with pytest.raises(Exception, match="Update failed"):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_commit_failure(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test handling of commit failure."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"
        mock_gitlab_client.update_file.side_effect = Exception("Commit failed")

        with pytest.raises(Exception, match="Commit failed"):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_create_rollback_mr_mr_creation_failure(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test handling of MR creation failure."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"
        mock_gitlab_client.create_merge_request.side_effect = Exception("MR creation failed")

        with pytest.raises(Exception, match="MR creation failed"):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )


class TestRollbackEngineFileOperations:
    """Tests for file operations in RollbackEngine."""

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("builtins.open", new_callable=mock_open, read_data="version: 1.19.0")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_temp_file_path_format(
        self,
        mock_unlink,
        mock_file,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that temporary file path includes timestamp."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        await rollback_engine.create_rollback_mr(
            cluster=sample_cluster,
            current_version="1.20.0",
            previous_version="1.19.0",
            failure_reason="Test failure",
        )

        # Verify update_version was called with temp file path
        update_call = rollback_engine.updater.update_version.call_args
        file_path = update_call[1]["file_path"]
        assert str(file_path).startswith("/tmp/rollback_")
        assert "20251020-143000" in str(file_path)
        assert str(file_path).endswith(".yaml")

    @pytest.mark.asyncio
    @patch("guard.rollback.engine.datetime")
    @patch("guard.rollback.engine.Path.unlink")
    async def test_file_operations_workflow(
        self,
        mock_unlink,
        mock_datetime,
        rollback_engine,
        sample_cluster,
        mock_gitlab_client,
    ):
        """Test that file operations happen in correct order."""
        mock_datetime.utcnow.return_value.strftime.return_value = "20251020-143000"

        original_content = "spec:\n  chart:\n    spec:\n      version: '1.20.0'\n"
        mock_gitlab_client.get_file.return_value = original_content

        with patch("builtins.open", mock_open(read_data="updated version: 1.19.0")):
            await rollback_engine.create_rollback_mr(
                cluster=sample_cluster,
                current_version="1.20.0",
                previous_version="1.19.0",
                failure_reason="Test failure",
            )

        # Verify that file was retrieved, updated, and committed
        mock_gitlab_client.get_file.assert_called_once()
        rollback_engine.updater.update_version.assert_called_once()
        mock_gitlab_client.update_file.assert_called_once()
