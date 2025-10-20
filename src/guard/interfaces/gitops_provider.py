"""GitOps provider interface for version control operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MergeRequestInfo:
    """Normalized merge request information."""

    id: int
    iid: int
    title: str
    description: str
    source_branch: str
    target_branch: str
    state: str
    web_url: str
    created_at: datetime
    updated_at: datetime


class GitOpsProvider(ABC):
    """Abstract interface for GitOps operations.

    This interface abstracts version control operations (GitLab, GitHub, etc.)
    providing unified access to repository and merge request operations.

    Design Philosophy:
    - Hide VCS-specific implementation details
    - Return normalized data structures
    - Support both GitLab and GitHub workflows
    """

    @abstractmethod
    async def create_branch(self, repository: str, branch_name: str, ref: str = "main") -> str:
        """Create a new branch.

        Args:
            repository: Repository identifier (GitLab: numeric ID or path, GitHub: owner/repo)
            branch_name: Name for new branch
            ref: Reference to branch from (default: main)

        Returns:
            Branch name

        Raises:
            GitOpsProviderError: If branch creation fails
        """

    @abstractmethod
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

    @abstractmethod
    async def update_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str
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

    @abstractmethod
    async def create_merge_request(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        draft: bool = True,
        assignees: list[str] | None = None,
    ) -> MergeRequestInfo:
        """Create a merge request.

        Args:
            project_id: Project identifier
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description
            draft: Create as draft (default: True)
            assignees: Optional list of user identifiers (usernames or IDs) to assign

        Returns:
            Normalized merge request information

        Raises:
            GitOpsProviderError: If MR creation fails
        """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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
