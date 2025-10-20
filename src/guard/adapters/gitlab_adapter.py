"""GitLab adapter implementing GitOpsProvider interface."""

from datetime import datetime

from gitlab.exceptions import GitlabError

from guard.clients.gitlab_client import GitLabClient
from guard.interfaces.exceptions import GitOpsProviderError
from guard.interfaces.gitops_provider import GitOpsProvider, MergeRequestInfo
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class GitLabAdapter(GitOpsProvider):
    """Adapter wrapping GitLabClient to implement GitOpsProvider interface.

    This adapter normalizes GitLab API responses and provides a clean
    interface for GitOps operations.
    """

    def __init__(self, url: str, token: str):
        """Initialize GitLab adapter.

        Args:
            url: GitLab instance URL
            token: Private access token
        """
        try:
            self.client = GitLabClient(url=url, token=token)
            logger.debug("gitlab_adapter_initialized", url=url)
        except Exception as e:
            raise GitOpsProviderError(f"Failed to initialize GitLab adapter: {e}") from e

    async def create_branch(self, project_id: str, branch_name: str, ref: str = "main") -> str:
        """Create a new branch.

        Args:
            project_id: Project identifier
            branch_name: Name for new branch
            ref: Reference to branch from

        Returns:
            Branch name

        Raises:
            GitOpsProviderError: If branch creation fails
        """
        try:
            branch = self.client.create_branch(project_id, branch_name, ref)
            return branch.name
        except Exception as e:
            logger.error("create_branch_failed", branch_name=branch_name, error=str(e))
            raise GitOpsProviderError(f"Failed to create branch {branch_name}: {e}") from e

    async def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Get file contents from repository.

        Args:
            project_id: Project identifier
            file_path: Path to file in repository
            ref: Branch/tag/commit reference

        Returns:
            File contents as string

        Raises:
            GitOpsProviderError: If file cannot be retrieved
        """
        try:
            return self.client.get_file(project_id, file_path, ref)
        except Exception as e:
            logger.error("get_file_content_failed", file_path=file_path, error=str(e))
            raise GitOpsProviderError(f"Failed to get file {file_path}: {e}") from e

    async def update_file(
        self,
        project_id: str,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str,
    ) -> bool:
        """Update (or create) a file in the repository.

        Args:
            project_id: Project identifier
            file_path: Path to file in repository
            content: New file content
            commit_message: Commit message
            branch: Branch to commit to

        Returns:
            True if successful

        Raises:
            GitOpsProviderError: If update fails
        """
        try:
            self.client.update_file(project_id, file_path, content, commit_message, branch)
            return True
        except Exception as e:
            logger.error("update_file_failed", file_path=file_path, error=str(e))
            raise GitOpsProviderError(f"Failed to update file {file_path}: {e}") from e

    async def create_merge_request(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        draft: bool = True,
        assignee_ids: list[int] | None = None,
    ) -> MergeRequestInfo:
        """Create a merge request.

        Args:
            project_id: Project identifier
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description
            draft: Create as draft
            assignee_ids: Optional list of user IDs to assign

        Returns:
            Normalized merge request information

        Raises:
            GitOpsProviderError: If MR creation fails
        """
        try:
            assignee_id = assignee_ids[0] if assignee_ids else None
            mr = self.client.create_merge_request(
                project_id,
                source_branch,
                target_branch,
                title,
                description,
                assignee_id=assignee_id,
                draft=draft,
            )

            # Normalize to MergeRequestInfo
            return MergeRequestInfo(
                id=mr.id,
                iid=mr.iid,
                title=mr.title,
                description=mr.description,
                source_branch=mr.source_branch,
                target_branch=mr.target_branch,
                state=mr.state,
                web_url=mr.web_url,
                created_at=datetime.fromisoformat(mr.created_at.replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(mr.updated_at.replace("Z", "+00:00")),
            )

        except Exception as e:
            logger.error(
                "create_merge_request_failed",
                source_branch=source_branch,
                error=str(e),
            )
            raise GitOpsProviderError(f"Failed to create MR from {source_branch}: {e}") from e

    async def get_merge_request(self, project_id: str, mr_id: int) -> MergeRequestInfo:
        """Get merge request information.

        Args:
            project_id: Project identifier
            mr_id: MR ID or IID

        Returns:
            Normalized merge request information

        Raises:
            GitOpsProviderError: If MR cannot be retrieved
        """
        try:
            mr = self.client.get_merge_request(project_id, mr_id)

            return MergeRequestInfo(
                id=mr.id,
                iid=mr.iid,
                title=mr.title,
                description=mr.description,
                source_branch=mr.source_branch,
                target_branch=mr.target_branch,
                state=mr.state,
                web_url=mr.web_url,
                created_at=datetime.fromisoformat(mr.created_at.replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(mr.updated_at.replace("Z", "+00:00")),
            )

        except Exception as e:
            logger.error("get_merge_request_failed", mr_id=mr_id, error=str(e))
            raise GitOpsProviderError(f"Failed to get MR {mr_id}: {e}") from e

    async def add_merge_request_comment(self, project_id: str, mr_id: int, comment: str) -> bool:
        """Add a comment to a merge request.

        Args:
            project_id: Project identifier
            mr_id: MR ID or IID
            comment: Comment text

        Returns:
            True if successful

        Raises:
            GitOpsProviderError: If comment creation fails
        """
        try:
            self.client.add_mr_comment(project_id, mr_id, comment)
            return True
        except Exception as e:
            logger.error("add_mr_comment_failed", mr_id=mr_id, error=str(e))
            raise GitOpsProviderError(f"Failed to add comment to MR {mr_id}: {e}") from e

    async def check_branch_exists(self, project_id: str, branch_name: str) -> bool:
        """Check if a branch exists.

        Args:
            project_id: Project identifier
            branch_name: Branch name to check

        Returns:
            True if branch exists

        Raises:
            GitOpsProviderError: If check fails
        """
        try:
            project = self.client.get_project(project_id)
            try:
                project.branches.get(branch_name)
                return True
            except GitlabError:
                return False
        except Exception as e:
            logger.error("check_branch_exists_failed", branch_name=branch_name, error=str(e))
            raise GitOpsProviderError(f"Failed to check if branch {branch_name} exists: {e}") from e
