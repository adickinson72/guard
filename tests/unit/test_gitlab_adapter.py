"""Unit tests for GitLabAdapter.

Tests the GitLab adapter implementation of GitOpsProvider interface.
All GitLab API calls are mocked to ensure tests are isolated and fast.
"""

from unittest.mock import MagicMock, patch

import pytest
from gitlab.exceptions import GitlabError

from guard.adapters.gitlab_adapter import GitLabAdapter
from guard.interfaces.exceptions import GitOpsProviderError
from guard.interfaces.gitops_provider import MergeRequestInfo


class TestGitLabAdapterInit:
    """Tests for GitLabAdapter initialization."""

    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    def test_init_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful adapter initialization."""
        mock_client = MagicMock()
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        mock_gitlab_client_class.assert_called_once_with(
            url="https://gitlab.com", token="test-token"
        )
        assert adapter.client == mock_client

    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    def test_init_failure_raises_gitops_provider_error(
        self, mock_gitlab_client_class: MagicMock
    ) -> None:
        """Test initialization failure raises GitOpsProviderError."""
        mock_gitlab_client_class.side_effect = Exception("Invalid token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            GitLabAdapter(url="https://gitlab.com", token="bad-token")

        assert "Failed to initialize GitLab adapter" in str(exc_info.value)


class TestGitLabAdapterCreateBranch:
    """Tests for create_branch method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_branch_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful branch creation."""
        mock_client = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "feature/istio-1.20.0-test"
        mock_client.create_branch.return_value = mock_branch
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.create_branch(
            project_id="infra/k8s-clusters", branch_name="feature/istio-1.20.0-test", ref="main"
        )

        mock_client.create_branch.assert_called_once_with(
            "infra/k8s-clusters", "feature/istio-1.20.0-test", "main"
        )
        assert result == "feature/istio-1.20.0-test"

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_branch_from_custom_ref(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test branch creation from custom reference."""
        mock_client = MagicMock()
        mock_branch = MagicMock()
        mock_branch.name = "hotfix/urgent-fix"
        mock_client.create_branch.return_value = mock_branch
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.create_branch(
            project_id="123", branch_name="hotfix/urgent-fix", ref="v1.19.0"
        )

        mock_client.create_branch.assert_called_once_with("123", "hotfix/urgent-fix", "v1.19.0")
        assert result == "hotfix/urgent-fix"

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_branch_failure(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test branch creation failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.create_branch.side_effect = Exception("Branch already exists")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.create_branch(project_id="123", branch_name="existing-branch", ref="main")

        assert "Failed to create branch" in str(exc_info.value)


class TestGitLabAdapterGetFileContent:
    """Tests for get_file_content method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_get_file_content_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful file content retrieval."""
        mock_client = MagicMock()
        mock_client.get_file.return_value = "apiVersion: v1\nkind: HelmRelease"
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.get_file_content(
            project_id="123", file_path="clusters/prod/istio-helmrelease.yaml", ref="main"
        )

        mock_client.get_file.assert_called_once_with(
            "123", "clusters/prod/istio-helmrelease.yaml", "main"
        )
        assert "apiVersion" in result

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_get_file_content_failure(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test file content retrieval failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.get_file.side_effect = Exception("File not found")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.get_file_content(
                project_id="123", file_path="nonexistent.yaml", ref="main"
            )

        assert "Failed to get file" in str(exc_info.value)


class TestGitLabAdapterUpdateFile:
    """Tests for update_file method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_update_file_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful file update."""
        mock_client = MagicMock()
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.update_file(
            project_id="123",
            file_path="config.yaml",
            content="updated: content",
            commit_message="Update config",
            branch="feature/update-config",
        )

        mock_client.update_file.assert_called_once_with(
            "123", "config.yaml", "updated: content", "Update config", "feature/update-config"
        )
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_update_file_failure(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test file update failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.update_file.side_effect = Exception("Update failed")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.update_file(
                project_id="123",
                file_path="config.yaml",
                content="content",
                commit_message="Update",
                branch="main",
            )

        assert "Failed to update file" in str(exc_info.value)


class TestGitLabAdapterCreateMergeRequest:
    """Tests for create_merge_request method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_merge_request_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful merge request creation."""
        mock_client = MagicMock()
        mock_mr = MagicMock()
        mock_mr.id = 456
        mock_mr.iid = 789
        mock_mr.title = "Istio upgrade to v1.20.0"
        mock_mr.description = "Automated upgrade"
        mock_mr.source_branch = "feature/istio-1.20.0"
        mock_mr.target_branch = "main"
        mock_mr.state = "opened"
        mock_mr.web_url = "https://gitlab.com/infra/k8s-clusters/-/merge_requests/789"
        mock_mr.created_at = "2024-01-01T12:00:00Z"
        mock_mr.updated_at = "2024-01-01T12:00:00Z"
        mock_client.create_merge_request.return_value = mock_mr
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.create_merge_request(
            project_id="123",
            source_branch="feature/istio-1.20.0",
            target_branch="main",
            title="Istio upgrade to v1.20.0",
            description="Automated upgrade",
            draft=True,
            assignee_ids=[100],
        )

        mock_client.create_merge_request.assert_called_once_with(
            "123",
            "feature/istio-1.20.0",
            "main",
            "Istio upgrade to v1.20.0",
            "Automated upgrade",
            assignee_id=100,
            draft=True,
        )

        assert isinstance(result, MergeRequestInfo)
        assert result.id == 456
        assert result.iid == 789
        assert result.title == "Istio upgrade to v1.20.0"
        assert result.state == "opened"

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_merge_request_without_assignee(
        self, mock_gitlab_client_class: MagicMock
    ) -> None:
        """Test MR creation without assignee."""
        mock_client = MagicMock()
        mock_mr = MagicMock()
        mock_mr.id = 456
        mock_mr.iid = 789
        mock_mr.title = "Test MR"
        mock_mr.description = "Test"
        mock_mr.source_branch = "feature/test"
        mock_mr.target_branch = "main"
        mock_mr.state = "opened"
        mock_mr.web_url = "https://gitlab.com/test/-/merge_requests/789"
        mock_mr.created_at = "2024-01-01T12:00:00Z"
        mock_mr.updated_at = "2024-01-01T12:00:00Z"
        mock_client.create_merge_request.return_value = mock_mr
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        await adapter.create_merge_request(
            project_id="123",
            source_branch="feature/test",
            target_branch="main",
            title="Test MR",
            description="Test",
            draft=False,
        )

        # Should pass assignee_id=None
        mock_client.create_merge_request.assert_called_once_with(
            "123", "feature/test", "main", "Test MR", "Test", assignee_id=None, draft=False
        )

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_create_merge_request_failure(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test MR creation failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.create_merge_request.side_effect = Exception("MR creation failed")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.create_merge_request(
                project_id="123",
                source_branch="feature/test",
                target_branch="main",
                title="Test",
                description="Test",
            )

        assert "Failed to create MR" in str(exc_info.value)


class TestGitLabAdapterGetMergeRequest:
    """Tests for get_merge_request method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_get_merge_request_success(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test successful MR retrieval."""
        mock_client = MagicMock()
        mock_mr = MagicMock()
        mock_mr.id = 456
        mock_mr.iid = 789
        mock_mr.title = "Test MR"
        mock_mr.description = "Test description"
        mock_mr.source_branch = "feature/test"
        mock_mr.target_branch = "main"
        mock_mr.state = "merged"
        mock_mr.web_url = "https://gitlab.com/test/-/merge_requests/789"
        mock_mr.created_at = "2024-01-01T12:00:00Z"
        mock_mr.updated_at = "2024-01-02T12:00:00Z"
        mock_client.get_merge_request.return_value = mock_mr
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.get_merge_request(project_id="123", mr_id=789)

        mock_client.get_merge_request.assert_called_once_with("123", 789)
        assert isinstance(result, MergeRequestInfo)
        assert result.id == 456
        assert result.iid == 789
        assert result.state == "merged"

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_get_merge_request_failure(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test MR retrieval failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.get_merge_request.side_effect = Exception("MR not found")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.get_merge_request(project_id="123", mr_id=999)

        assert "Failed to get MR" in str(exc_info.value)


class TestGitLabAdapterAddMergeRequestComment:
    """Tests for add_merge_request_comment method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_add_merge_request_comment_success(
        self, mock_gitlab_client_class: MagicMock
    ) -> None:
        """Test successful MR comment addition."""
        mock_client = MagicMock()
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.add_merge_request_comment(
            project_id="123", mr_id=789, comment="Validation passed successfully"
        )

        mock_client.add_mr_comment.assert_called_once_with(
            "123", 789, "Validation passed successfully"
        )
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_add_merge_request_comment_failure(
        self, mock_gitlab_client_class: MagicMock
    ) -> None:
        """Test MR comment addition failure raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.add_mr_comment.side_effect = Exception("Comment failed")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.add_merge_request_comment(
                project_id="123", mr_id=789, comment="Test comment"
            )

        assert "Failed to add comment to MR" in str(exc_info.value)


class TestGitLabAdapterCheckBranchExists:
    """Tests for check_branch_exists method."""

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_check_branch_exists_true(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test checking for existing branch returns True."""
        mock_client = MagicMock()
        mock_project = MagicMock()
        mock_branch = MagicMock()
        mock_project.branches.get.return_value = mock_branch
        mock_client.get_project.return_value = mock_project
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.check_branch_exists(project_id="123", branch_name="main")

        mock_client.get_project.assert_called_once_with("123")
        mock_project.branches.get.assert_called_once_with("main")
        assert result is True

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_check_branch_exists_false(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test checking for non-existing branch returns False."""
        mock_client = MagicMock()
        mock_project = MagicMock()
        mock_project.branches.get.side_effect = GitlabError("Branch not found")
        mock_client.get_project.return_value = mock_project
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        result = await adapter.check_branch_exists(
            project_id="123", branch_name="nonexistent-branch"
        )

        assert result is False

    @pytest.mark.asyncio
    @patch("guard.adapters.gitlab_adapter.GitLabClient")
    async def test_check_branch_exists_error(self, mock_gitlab_client_class: MagicMock) -> None:
        """Test branch existence check with unexpected error raises GitOpsProviderError."""
        mock_client = MagicMock()
        mock_client.get_project.side_effect = Exception("Project not found")
        mock_gitlab_client_class.return_value = mock_client

        adapter = GitLabAdapter(url="https://gitlab.com", token="test-token")

        with pytest.raises(GitOpsProviderError) as exc_info:
            await adapter.check_branch_exists(project_id="999", branch_name="main")

        assert "Failed to check if branch" in str(exc_info.value)
