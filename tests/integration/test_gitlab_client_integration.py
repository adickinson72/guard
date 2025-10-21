"""Integration tests for GitLab client."""

import os

import pytest

from guard.clients.gitlab_client import GitLabClient
from guard.core.exceptions import GitOpsError


@pytest.mark.integration
class TestGitLabClientIntegration:
    """Integration tests for GitLabClient with real GitLab API."""

    @pytest.fixture
    def gitlab_client(self, gitlab_test_token: str | None, skip_if_no_gitlab_token):
        """Create GitLab client for integration tests."""
        gitlab_url = os.getenv("GITLAB_TEST_URL", "https://gitlab.com")
        return GitLabClient(url=gitlab_url, token=gitlab_test_token)

    @pytest.fixture
    def test_project_id(self) -> str:
        """Get test project ID from environment.

        Set GITLAB_TEST_PROJECT_ID to a project you have access to for testing.
        Example: "mygroup/myproject" or "12345"
        """
        project_id = os.getenv("GITLAB_TEST_PROJECT_ID")
        if not project_id:
            pytest.skip(
                "GITLAB_TEST_PROJECT_ID not set. "
                "Set this to a project you have access to for testing."
            )
        return project_id

    def test_client_authentication(self, gitlab_client: GitLabClient):
        """Test that client authenticates successfully."""
        # Client should be authenticated (auth happens in __init__)
        assert gitlab_client.gl is not None
        assert gitlab_client.gl.user is not None

    def test_get_current_user(self, gitlab_client: GitLabClient):
        """Test retrieving current authenticated user."""
        user = gitlab_client.gl.user
        assert user is not None
        assert hasattr(user, "username")
        assert hasattr(user, "id")

    def test_get_project(self, gitlab_client: GitLabClient, test_project_id: str):
        """Test retrieving a project."""
        project = gitlab_client.get_project(test_project_id)

        assert project is not None
        assert hasattr(project, "id")
        assert hasattr(project, "name")
        assert hasattr(project, "path_with_namespace")
        assert hasattr(project, "default_branch")

    def test_get_project_invalid_id(self, gitlab_client: GitLabClient):
        """Test getting project with invalid ID raises error."""
        with pytest.raises(GitOpsError) as exc_info:
            gitlab_client.get_project("nonexistent/invalid-project-12345")

        assert "Failed to get project" in str(exc_info.value)

    def test_list_merge_requests(self, gitlab_client: GitLabClient, test_project_id: str):
        """Test listing merge requests for a project."""
        mrs = gitlab_client.list_merge_requests(test_project_id, state="opened")

        # Should return a list (may be empty)
        assert isinstance(mrs, list)

    def test_get_file_from_main_branch(self, gitlab_client: GitLabClient, test_project_id: str):
        """Test retrieving a file from the main branch."""
        # Try to get README or any common file
        file_paths_to_try = ["README.md", "README", ".gitignore", "LICENSE"]

        file_retrieved = False
        for file_path in file_paths_to_try:
            try:
                content = gitlab_client.get_file(test_project_id, file_path, ref="main")
                assert isinstance(content, str)
                assert len(content) > 0
                file_retrieved = True
                break
            except GitOpsError:
                continue

        if not file_retrieved:
            pytest.skip(
                f"Could not find any common files ({', '.join(file_paths_to_try)}) "
                "in test project for integration testing"
            )

    def test_get_nonexistent_file(self, gitlab_client: GitLabClient, test_project_id: str):
        """Test retrieving non-existent file raises error."""
        with pytest.raises(GitOpsError) as exc_info:
            gitlab_client.get_file(
                test_project_id, "this-file-does-not-exist-12345.txt", ref="main"
            )

        assert "Failed to get file" in str(exc_info.value)

    def test_user_lookup(self, gitlab_client: GitLabClient):
        """Test looking up user by username."""
        # Get current user's username and look it up
        current_user = gitlab_client.gl.user
        current_username = current_user.username

        user_id = gitlab_client.get_user_id_by_username(current_username)

        assert user_id is not None
        assert user_id == current_user.id

    def test_user_lookup_with_at_sign(self, gitlab_client: GitLabClient):
        """Test looking up user with @ prefix in username."""
        current_user = gitlab_client.gl.user
        current_username = current_user.username

        # Add @ prefix
        user_id = gitlab_client.get_user_id_by_username(f"@{current_username}")

        assert user_id is not None
        assert user_id == current_user.id

    def test_user_lookup_nonexistent(self, gitlab_client: GitLabClient):
        """Test looking up non-existent user returns None."""
        user_id = gitlab_client.get_user_id_by_username("nonexistent-user-12345-test")

        assert user_id is None


@pytest.mark.integration
@pytest.mark.slow
class TestGitLabClientWriteOperations:
    """Integration tests for write operations (branch, file, MR creation).

    These tests require write access to the test project and will skip if
    GITLAB_TEST_ALLOW_WRITE is not set to 'true'.
    """

    @pytest.fixture
    def gitlab_client(self, gitlab_test_token: str | None, skip_if_no_gitlab_token):
        """Create GitLab client for integration tests."""
        gitlab_url = os.getenv("GITLAB_TEST_URL", "https://gitlab.com")
        return GitLabClient(url=gitlab_url, token=gitlab_test_token)

    @pytest.fixture
    def test_project_id(self) -> str:
        """Get test project ID from environment."""
        project_id = os.getenv("GITLAB_TEST_PROJECT_ID")
        if not project_id:
            pytest.skip("GITLAB_TEST_PROJECT_ID not set")
        return project_id

    @pytest.fixture
    def skip_if_write_not_allowed(self):
        """Skip test if write operations are not explicitly allowed."""
        if os.getenv("GITLAB_TEST_ALLOW_WRITE", "").lower() != "true":
            pytest.skip("Write operations not allowed. Set GITLAB_TEST_ALLOW_WRITE=true to enable.")

    def test_create_and_delete_branch(
        self,
        gitlab_client: GitLabClient,
        test_project_id: str,
        skip_if_write_not_allowed,
    ):
        """Test creating and deleting a test branch."""
        import time

        test_branch_name = f"test-branch-{int(time.time())}"

        # Create branch
        branch = gitlab_client.create_branch(test_project_id, test_branch_name, ref="main")
        assert branch is not None
        assert branch.name == test_branch_name

        # Clean up: delete the branch
        try:
            project = gitlab_client.get_project(test_project_id)
            project.branches.delete(test_branch_name)
        except Exception as e:
            pytest.fail(f"Failed to clean up test branch: {e}")

    def test_create_file_in_branch(
        self,
        gitlab_client: GitLabClient,
        test_project_id: str,
        skip_if_write_not_allowed,
    ):
        """Test creating a file in a new branch."""
        import time

        test_branch_name = f"test-branch-{int(time.time())}"
        test_file_path = "test-file.txt"
        test_content = "This is a test file created by integration tests"

        try:
            # Create branch first
            gitlab_client.create_branch(test_project_id, test_branch_name, ref="main")

            # Create file in the branch
            gitlab_client.update_file(
                project_id=test_project_id,
                file_path=test_file_path,
                content=test_content,
                commit_message="Add test file",
                branch=test_branch_name,
            )

            # Verify file was created
            retrieved_content = gitlab_client.get_file(
                test_project_id, test_file_path, ref=test_branch_name
            )
            assert retrieved_content == test_content

        finally:
            # Clean up: delete the branch
            try:
                project = gitlab_client.get_project(test_project_id)
                project.branches.delete(test_branch_name)
            except Exception:
                pass  # Best effort cleanup
