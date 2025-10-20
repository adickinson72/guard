"""GitLab client for repository and MR operations."""

from typing import Any

import gitlab
from gitlab.exceptions import GitlabError

from guard.core.exceptions import GitOpsError
from guard.utils.logging import get_logger
from guard.utils.rate_limiter import rate_limited
from guard.utils.retry import retry_on_exception

logger = get_logger(__name__)


class GitLabClient:
    """GitLab API client wrapper."""

    def __init__(self, url: str, token: str):
        """Initialize GitLab client.

        Args:
            url: GitLab instance URL
            token: Private access token
        """
        self.url = url
        self.gl = gitlab.Gitlab(url, private_token=token)

        try:
            self.gl.auth()
            logger.debug("gitlab_client_initialized", url=url)
        except GitlabError as e:
            logger.error("gitlab_auth_failed", url=url, error=str(e))
            raise GitOpsError(f"Failed to authenticate with GitLab: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def get_project(self, project_id: str | int) -> Any:
        """Get a GitLab project.

        Args:
            project_id: Project ID or path (e.g., "group/project")

        Returns:
            Project object

        Raises:
            GitOpsError: If project cannot be retrieved
        """
        try:
            logger.debug("getting_project", project_id=project_id)
            project = self.gl.projects.get(project_id)
            logger.info("project_retrieved", project_id=project_id)
            return project

        except GitlabError as e:
            logger.error("get_project_failed", project_id=project_id, error=str(e))
            raise GitOpsError(f"Failed to get project {project_id}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def create_branch(self, project_id: str | int, branch_name: str, ref: str = "main") -> Any:
        """Create a new branch.

        Args:
            project_id: Project ID or path
            branch_name: Name for the new branch
            ref: Reference to branch from (default: main)

        Returns:
            Branch object

        Raises:
            GitOpsError: If branch creation fails
        """
        try:
            logger.debug(
                "creating_branch",
                project_id=project_id,
                branch_name=branch_name,
                ref=ref,
            )

            project = self.get_project(project_id)
            branch = project.branches.create({"branch": branch_name, "ref": ref})

            logger.info("branch_created", branch_name=branch_name)
            return branch

        except GitlabError as e:
            logger.error(
                "create_branch_failed",
                branch_name=branch_name,
                error=str(e),
            )
            raise GitOpsError(f"Failed to create branch {branch_name}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def get_file(self, project_id: str | int, file_path: str, ref: str = "main") -> str:
        """Get file contents from repository.

        Args:
            project_id: Project ID or path
            file_path: Path to file in repository
            ref: Branch/tag/commit reference

        Returns:
            File contents as string

        Raises:
            GitOpsError: If file cannot be retrieved
        """
        try:
            logger.debug(
                "getting_file",
                project_id=project_id,
                file_path=file_path,
                ref=ref,
            )

            project = self.get_project(project_id)
            file = project.files.get(file_path=file_path, ref=ref)

            # Decode file content
            content = file.decode().decode("utf-8")

            logger.info("file_retrieved", file_path=file_path)
            return content

        except GitlabError as e:
            logger.error(
                "get_file_failed",
                file_path=file_path,
                error=str(e),
            )
            raise GitOpsError(f"Failed to get file {file_path}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def update_file(
        self,
        project_id: str | int,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str,
    ) -> Any:
        """Update a file in the repository.

        Args:
            project_id: Project ID or path
            file_path: Path to file in repository
            content: New file content
            commit_message: Commit message
            branch: Branch to commit to

        Returns:
            Commit object

        Raises:
            GitOpsError: If file update fails
        """
        try:
            logger.debug(
                "updating_file",
                project_id=project_id,
                file_path=file_path,
                branch=branch,
            )

            project = self.get_project(project_id)

            # Try to get existing file
            try:
                file = project.files.get(file_path=file_path, ref=branch)
                file.content = content
                file.save(branch=branch, commit_message=commit_message)
                logger.info("file_updated", file_path=file_path)
                return file

            except GitlabError:
                # File doesn't exist, create it
                file = project.files.create(
                    {
                        "file_path": file_path,
                        "branch": branch,
                        "content": content,
                        "commit_message": commit_message,
                    }
                )
                logger.info("file_created", file_path=file_path)
                return file

        except GitlabError as e:
            logger.error(
                "update_file_failed",
                file_path=file_path,
                error=str(e),
            )
            raise GitOpsError(f"Failed to update file {file_path}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def list_merge_requests(
        self,
        project_id: str | int,
        state: str = "opened",
        source_branch: str | None = None,
    ) -> list[Any]:
        """List merge requests for a project.

        Args:
            project_id: Project ID or path
            state: MR state to filter (opened, closed, merged, all)
            source_branch: Optional source branch filter

        Returns:
            List of MR objects

        Raises:
            GitOpsError: If listing fails
        """
        try:
            logger.debug(
                "listing_merge_requests",
                project_id=project_id,
                state=state,
                source_branch=source_branch,
            )

            project = self.get_project(project_id)

            filters = {"state": state}
            if source_branch:
                filters["source_branch"] = source_branch

            mrs = project.mergerequests.list(**filters)

            logger.info("merge_requests_listed", project_id=project_id, count=len(mrs))
            return mrs

        except GitlabError as e:
            logger.error(
                "list_merge_requests_failed",
                project_id=project_id,
                error=str(e),
            )
            raise GitOpsError(f"Failed to list MRs for {project_id}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def create_merge_request(
        self,
        project_id: str | int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        assignee_id: int | None = None,
        draft: bool = True,
        skip_if_exists: bool = True,
    ) -> Any:
        """Create a merge request with idempotency checks.

        Args:
            project_id: Project ID or path
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description
            assignee_id: User ID to assign (optional)
            draft: Create as draft MR (default: True)
            skip_if_exists: Skip creation if open MR exists (default: True)

        Returns:
            MR object (existing or newly created)

        Raises:
            GitOpsError: If MR creation fails
        """
        try:
            logger.debug(
                "creating_merge_request",
                project_id=project_id,
                source_branch=source_branch,
                target_branch=target_branch,
            )

            # Check for existing open MRs from the same source branch
            if skip_if_exists:
                existing_mrs = self.list_merge_requests(
                    project_id=project_id,
                    state="opened",
                    source_branch=source_branch,
                )

                if existing_mrs:
                    existing_mr = existing_mrs[0]
                    logger.info(
                        "merge_request_already_exists",
                        mr_iid=existing_mr.iid,
                        mr_url=existing_mr.web_url,
                        source_branch=source_branch,
                    )
                    return existing_mr

            project = self.get_project(project_id)

            mr_data: dict[str, Any] = {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": ("Draft: " + title) if draft else title,
                "description": description,
            }

            if assignee_id:
                mr_data["assignee_id"] = assignee_id

            mr = project.mergerequests.create(mr_data)

            logger.info(
                "merge_request_created",
                mr_iid=mr.iid,
                mr_url=mr.web_url,
            )

            return mr

        except GitlabError as e:
            logger.error(
                "create_merge_request_failed",
                source_branch=source_branch,
                error=str(e),
            )
            raise GitOpsError(f"Failed to create MR from {source_branch}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def get_merge_request(self, project_id: str | int, mr_iid: int) -> Any:
        """Get a merge request.

        Args:
            project_id: Project ID or path
            mr_iid: MR internal ID

        Returns:
            MR object

        Raises:
            GitOpsError: If MR cannot be retrieved
        """
        try:
            logger.debug("getting_merge_request", project_id=project_id, mr_iid=mr_iid)

            project = self.get_project(project_id)
            mr = project.mergerequests.get(mr_iid)

            logger.info("merge_request_retrieved", mr_iid=mr_iid)
            return mr

        except GitlabError as e:
            logger.error(
                "get_merge_request_failed",
                mr_iid=mr_iid,
                error=str(e),
            )
            raise GitOpsError(f"Failed to get MR {mr_iid}: {e}") from e

    @rate_limited("gitlab_api")
    @retry_on_exception(exceptions=(GitlabError,), max_attempts=3)
    def add_mr_comment(self, project_id: str | int, mr_iid: int, comment: str) -> Any:
        """Add a comment to a merge request.

        Args:
            project_id: Project ID or path
            mr_iid: MR internal ID
            comment: Comment text

        Returns:
            Note object

        Raises:
            GitOpsError: If comment creation fails
        """
        try:
            logger.debug("adding_mr_comment", project_id=project_id, mr_iid=mr_iid)

            mr = self.get_merge_request(project_id, mr_iid)
            note = mr.notes.create({"body": comment})

            logger.info("mr_comment_added", mr_iid=mr_iid)
            return note

        except GitlabError as e:
            logger.error(
                "add_mr_comment_failed",
                mr_iid=mr_iid,
                error=str(e),
            )
            raise GitOpsError(f"Failed to add comment to MR {mr_iid}: {e}") from e
