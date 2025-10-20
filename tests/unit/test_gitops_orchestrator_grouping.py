"""Unit tests for GitOpsOrchestrator cluster grouping functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from guard.core.models import ClusterConfig, ClusterMetadata, DatadogTags
from guard.gitops.gitops_orchestrator import GitOpsOrchestrator
from guard.interfaces.exceptions import PartialFailureError
from guard.interfaces.gitops_provider import MergeRequestInfo


@pytest.fixture
def sample_clusters():
    """Create sample cluster configurations."""
    return [
        ClusterConfig(
            cluster_id="cluster-1",
            batch_id="prod-wave-1",
            environment="production",
            region="us-east-1",
            gitlab_repo="devops/k8s-prod",
            flux_config_path="clusters/prod/istio/helmrelease.yaml",
            aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-1",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="cluster-1", env="prod"),
            owner_team="platform",
            owner_handle="platform-team",
            metadata=ClusterMetadata(),
        ),
        ClusterConfig(
            cluster_id="cluster-2",
            batch_id="prod-wave-1",
            environment="production",
            region="us-west-2",
            gitlab_repo="devops/k8s-prod",
            flux_config_path="clusters/prod/istio/helmrelease.yaml",  # Same repo+path
            aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-2",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="cluster-2", env="prod"),
            owner_team="platform",
            owner_handle="platform-team",
            metadata=ClusterMetadata(),
        ),
        ClusterConfig(
            cluster_id="cluster-3",
            batch_id="prod-wave-2",
            environment="production",
            region="eu-west-1",
            gitlab_repo="devops/k8s-eu",  # Different repo
            flux_config_path="clusters/prod/istio/helmrelease.yaml",
            aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-3",
            current_istio_version="1.19.0",
            datadog_tags=DatadogTags(cluster="cluster-3", env="prod"),
            owner_team="platform",
            owner_handle="platform-team",
            metadata=ClusterMetadata(),
        ),
    ]


@pytest.fixture
def mock_git_provider():
    """Create mock GitOpsProvider."""
    provider = MagicMock()
    provider.create_branch = AsyncMock()
    provider.get_file_content = AsyncMock(return_value="apiVersion: v1\nkind: HelmRelease")
    provider.update_file = AsyncMock()
    provider.create_merge_request = AsyncMock(
        return_value=MergeRequestInfo(
            id=1,
            iid=1,
            title="Test MR",
            description="Test",
            source_branch="test",
            target_branch="main",
            state="draft",
            web_url="https://gitlab.com/test/mr/1",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    return provider


@pytest.fixture
def mock_config_updater():
    """Create mock ConfigUpdater."""
    updater = MagicMock()
    updater.update_version = AsyncMock()
    return updater


@pytest.fixture
def orchestrator(mock_git_provider, mock_config_updater):
    """Create GitOpsOrchestrator instance."""
    return GitOpsOrchestrator(git_provider=mock_git_provider, config_updater=mock_config_updater)


class TestGroupClustersByRepoPath:
    """Tests for group_clusters_by_repo_path static method."""

    def test_group_single_cluster(self, sample_clusters):
        """Test grouping single cluster."""
        grouped = GitOpsOrchestrator.group_clusters_by_repo_path([sample_clusters[0]])

        assert len(grouped) == 1
        key = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        assert key in grouped
        assert len(grouped[key]) == 1
        assert grouped[key][0].cluster_id == "cluster-1"

    def test_group_clusters_same_repo_and_path(self, sample_clusters):
        """Test grouping clusters with same repo and path."""
        # cluster-1 and cluster-2 share the same repo and path
        grouped = GitOpsOrchestrator.group_clusters_by_repo_path(sample_clusters[:2])

        assert len(grouped) == 1
        key = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        assert key in grouped
        assert len(grouped[key]) == 2
        cluster_ids = {c.cluster_id for c in grouped[key]}
        assert cluster_ids == {"cluster-1", "cluster-2"}

    def test_group_clusters_different_repos(self, sample_clusters):
        """Test grouping clusters with different repos."""
        # All three clusters - two share repo+path, one is different
        grouped = GitOpsOrchestrator.group_clusters_by_repo_path(sample_clusters)

        assert len(grouped) == 2

        # First group: cluster-1 and cluster-2
        key1 = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        assert key1 in grouped
        assert len(grouped[key1]) == 2

        # Second group: cluster-3
        key2 = ("devops/k8s-eu", "clusters/prod/istio/helmrelease.yaml")
        assert key2 in grouped
        assert len(grouped[key2]) == 1
        assert grouped[key2][0].cluster_id == "cluster-3"

    def test_group_empty_list(self):
        """Test grouping empty list of clusters."""
        grouped = GitOpsOrchestrator.group_clusters_by_repo_path([])

        assert len(grouped) == 0
        assert grouped == {}

    def test_group_clusters_different_paths_same_repo(self):
        """Test grouping clusters with different paths in same repo."""
        clusters = [
            ClusterConfig(
                cluster_id="cluster-1",
                batch_id="prod",
                environment="production",
                region="us-east-1",
                gitlab_repo="devops/k8s-prod",
                flux_config_path="path/to/config1.yaml",
                aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-1",
                current_istio_version="1.19.0",
                datadog_tags=DatadogTags(cluster="cluster-1", env="prod"),
                owner_team="platform",
                owner_handle="platform-team",
                metadata=ClusterMetadata(),
            ),
            ClusterConfig(
                cluster_id="cluster-2",
                batch_id="prod",
                environment="production",
                region="us-east-1",
                gitlab_repo="devops/k8s-prod",  # Same repo
                flux_config_path="path/to/config2.yaml",  # Different path
                aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-2",
                current_istio_version="1.19.0",
                datadog_tags=DatadogTags(cluster="cluster-2", env="prod"),
                owner_team="platform",
                owner_handle="platform-team",
                metadata=ClusterMetadata(),
            ),
        ]

        grouped = GitOpsOrchestrator.group_clusters_by_repo_path(clusters)

        # Should create two groups despite same repo
        assert len(grouped) == 2


class TestCreateUpgradeMrsForBatch:
    """Tests for create_upgrade_mrs_for_batch method."""

    @pytest.mark.asyncio
    async def test_create_mr_for_single_group(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test creating MR for a single group."""
        # Use only cluster-1
        mr_infos = await orchestrator.create_upgrade_mrs_for_batch([sample_clusters[0]], "1.20.0")

        assert len(mr_infos) == 1
        key = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        assert key in mr_infos

        # Verify Git operations were called
        mock_git_provider.create_branch.assert_called_once()
        mock_git_provider.get_file_content.assert_called_once()
        mock_git_provider.update_file.assert_called_once()
        mock_git_provider.create_merge_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_mr_for_multiple_groups(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test creating MRs for multiple groups."""
        # Use all clusters - should create 2 MRs
        mr_infos = await orchestrator.create_upgrade_mrs_for_batch(sample_clusters, "1.20.0")

        assert len(mr_infos) == 2

        # Verify both groups got MRs
        key1 = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        key2 = ("devops/k8s-eu", "clusters/prod/istio/helmrelease.yaml")
        assert key1 in mr_infos
        assert key2 in mr_infos

        # Verify Git operations called twice (once per group)
        assert mock_git_provider.create_branch.call_count == 2
        assert mock_git_provider.create_merge_request.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_mr_clusters_listed_in_description(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test that batch MR description lists all clusters."""
        # Use cluster-1 and cluster-2 (same group)
        await orchestrator.create_upgrade_mrs_for_batch(sample_clusters[:2], "1.20.0")

        # Check MR description includes both clusters
        call_args = mock_git_provider.create_merge_request.call_args
        description = call_args.kwargs["description"]

        assert "cluster-1" in description
        assert "cluster-2" in description
        assert "2" in description  # Cluster count

    @pytest.mark.asyncio
    async def test_batch_mr_title_includes_cluster_count(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test that batch MR title includes cluster count."""
        await orchestrator.create_upgrade_mrs_for_batch(sample_clusters[:2], "1.20.0")

        call_args = mock_git_provider.create_merge_request.call_args
        title = call_args.kwargs["title"]

        assert "2 clusters" in title.lower()
        assert "1.20.0" in title

    @pytest.mark.asyncio
    @patch("guard.gitops.gitops_orchestrator.uuid.uuid4")
    @patch("guard.gitops.gitops_orchestrator.datetime")
    async def test_branch_name_includes_timestamp_and_uuid(
        self,
        mock_datetime,
        mock_uuid,
        orchestrator,
        sample_clusters,
        mock_git_provider,
    ):
        """Test that branch name includes timestamp and UUID."""
        # Mock timestamp and UUID
        mock_datetime.now.return_value.strftime.return_value = "20251019120000"
        mock_uuid.return_value = MagicMock()
        mock_uuid.return_value.__str__ = lambda x: "12345678-1234-5678-1234-567812345678"

        await orchestrator.create_upgrade_mrs_for_batch([sample_clusters[0]], "1.20.0")

        call_args = mock_git_provider.create_branch.call_args
        branch_name = call_args.kwargs["branch_name"]

        assert "20251019120000" in branch_name
        assert "12345678" in branch_name  # First 8 chars of UUID
        assert "upgrade/" in branch_name
        assert "1.20.0" in branch_name

    @pytest.mark.asyncio
    async def test_batch_mr_mixed_batches(self, orchestrator, mock_git_provider):
        """Test creating MR for clusters from different batches sharing repo+path."""
        clusters = [
            ClusterConfig(
                cluster_id="cluster-1",
                batch_id="batch-a",
                environment="production",
                region="us-east-1",
                gitlab_repo="devops/k8s-prod",
                flux_config_path="clusters/prod/istio/helmrelease.yaml",
                aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-1",
                current_istio_version="1.19.0",
                datadog_tags=DatadogTags(cluster="cluster-1", env="prod"),
                owner_team="platform",
                owner_handle="platform-team",
                metadata=ClusterMetadata(),
            ),
            ClusterConfig(
                cluster_id="cluster-2",
                batch_id="batch-b",  # Different batch
                environment="production",
                region="us-west-2",
                gitlab_repo="devops/k8s-prod",  # Same repo
                flux_config_path="clusters/prod/istio/helmrelease.yaml",  # Same path
                aws_role_arn="arn:aws:iam::123456789:role/eks-cluster-2",
                current_istio_version="1.19.0",
                datadog_tags=DatadogTags(cluster="cluster-2", env="prod"),
                owner_team="platform",
                owner_handle="platform-team",
                metadata=ClusterMetadata(),
            ),
        ]

        await orchestrator.create_upgrade_mrs_for_batch(clusters, "1.20.0")

        # Should still create single MR
        call_args = mock_git_provider.create_merge_request.call_args
        title = call_args.kwargs["title"]

        # Title should have combined batch name
        assert "batch-a-batch-b" in title.lower() or (
            "batch-a" in title.lower() and "batch-b" in title.lower()
        )

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, orchestrator, sample_clusters, mock_git_provider):
        """Test that dry-run mode doesn't create actual MRs."""
        mr_infos = await orchestrator.create_upgrade_mrs_for_batch(
            [sample_clusters[0]], "1.20.0", dry_run=True
        )

        assert len(mr_infos) == 1

        # Verify no Git operations were called
        mock_git_provider.create_branch.assert_not_called()
        mock_git_provider.update_file.assert_not_called()
        mock_git_provider.create_merge_request.assert_not_called()

        # Verify placeholder MR info returned
        key = ("devops/k8s-prod", "clusters/prod/istio/helmrelease.yaml")
        mr_info = mr_infos[key]
        assert mr_info.id == 0
        assert mr_info.web_url == ""

    @pytest.mark.asyncio
    async def test_draft_parameter_passed_to_create_mr(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test that draft parameter is passed to create_merge_request."""
        # Test with draft=True
        await orchestrator.create_upgrade_mrs_for_batch([sample_clusters[0]], "1.20.0", draft=True)

        call_args = mock_git_provider.create_merge_request.call_args
        assert call_args.kwargs["draft"] is True

        # Reset mock
        mock_git_provider.reset_mock()

        # Test with draft=False
        await orchestrator.create_upgrade_mrs_for_batch([sample_clusters[0]], "1.20.0", draft=False)

        call_args = mock_git_provider.create_merge_request.call_args
        assert call_args.kwargs["draft"] is False

    @pytest.mark.asyncio
    async def test_error_handling_partial_failure(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test that partial failures raise PartialFailureError."""
        # Make one call fail
        mock_git_provider.create_branch.side_effect = [
            None,  # First call succeeds
            Exception("Branch creation failed"),  # Second call fails
        ]

        # Should raise PartialFailureError when some MRs fail
        with pytest.raises(PartialFailureError) as exc_info:
            await orchestrator.create_upgrade_mrs_for_batch(sample_clusters, "1.20.0")

        # Verify exception details
        error = exc_info.value
        assert error.successful_items == 1
        assert error.failed_items == 1
        assert len(error.errors) == 1
        assert "Branch creation failed" in error.errors[0]

    @pytest.mark.asyncio
    async def test_commit_message_includes_cluster_list(
        self, orchestrator, sample_clusters, mock_git_provider
    ):
        """Test that commit message includes affected clusters."""
        await orchestrator.create_upgrade_mrs_for_batch(sample_clusters[:2], "1.20.0")

        call_args = mock_git_provider.update_file.call_args
        commit_message = call_args.kwargs["commit_message"]

        # Should mention cluster IDs
        assert "cluster-1" in commit_message or "cluster" in commit_message.lower()
        assert "1.20.0" in commit_message
