"""Rollback engine for automated rollback operations."""

from datetime import datetime
from pathlib import Path

from guard.clients.gitlab_client import GitLabClient
from guard.core.models import ClusterConfig
from guard.interfaces.config_updater import ConfigUpdater
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class RollbackEngine:
    """Engine for automated rollback operations."""

    def __init__(self, gitlab_client: GitLabClient, config_updater: ConfigUpdater):
        """Initialize rollback engine.

        Args:
            gitlab_client: GitLab client instance
            config_updater: Config updater for updating GitOps files
        """
        self.gitlab = gitlab_client
        self.updater = config_updater
        logger.debug("rollback_engine_initialized")

    async def create_rollback_mr(
        self,
        cluster: ClusterConfig,
        current_version: str,
        previous_version: str,
        failure_reason: str,
        failure_metrics: dict | None = None,
    ) -> str:
        """Create automated rollback MR.

        Args:
            cluster: Cluster configuration
            current_version: Failed version
            previous_version: Version to roll back to
            failure_reason: Reason for rollback
            failure_metrics: Failure metrics (optional)

        Returns:
            Rollback MR URL
        """
        logger.info(
            "creating_rollback_mr",
            cluster_id=cluster.cluster_id,
            current_version=current_version,
            previous_version=previous_version,
            reason=failure_reason,
        )

        # Generate rollback branch name with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        branch_name = f"rollback/istio-{cluster.batch_id}-{previous_version}-{timestamp}"

        # Get project and config file path from cluster config
        project_id = cluster.gitlab_repo
        config_path = cluster.flux_config_path

        try:
            # Create rollback branch from main
            logger.debug("creating_rollback_branch", branch_name=branch_name)
            self.gitlab.create_branch(
                project_id=project_id,
                branch_name=branch_name,
                ref="main",
            )

            # Get current file content
            logger.debug("fetching_flux_config", path=config_path)
            file_content = self.gitlab.get_file(
                project_id=project_id,
                file_path=config_path,
                ref=branch_name,
            )

            # Update version to previous version using injected updater
            config_file = Path(f"/tmp/rollback_{timestamp}.yaml")

            # Write current content to temp file
            with config_file.open("w") as f:
                f.write(file_content)

            # Update version
            await self.updater.update_version(
                file_path=config_file,
                target_version=previous_version,
                backup=False,
            )

            # Read updated content
            with config_file.open() as f:
                updated_content = f.read()

            # Clean up temp file
            config_file.unlink()

            # Commit changes
            commit_message = f"""Rollback Istio from {current_version} to {previous_version} for {cluster.batch_id}

Reason: {failure_reason}

This is an automated rollback created by GUARD.
"""

            if failure_metrics:
                metrics_str = "\n".join(f"- {k}: {v}" for k, v in failure_metrics.items())
                commit_message += f"\nFailure Metrics:\n{metrics_str}"

            logger.debug("committing_rollback_changes")
            self.gitlab.update_file(
                project_id=project_id,
                file_path=config_path,
                branch=branch_name,
                content=updated_content,
                commit_message=commit_message,
            )

            # Create MR
            mr_title = (
                f"[ROLLBACK] Istio {current_version} → {previous_version} ({cluster.batch_id})"
            )
            mr_description = f"""## Automated Rollback

**Cluster Batch**: {cluster.batch_id}
**Cluster ID**: {cluster.cluster_id}
**Rollback**: {current_version} → {previous_version}

### Failure Reason
{failure_reason}
"""

            if failure_metrics:
                mr_description += "\n### Failure Metrics\n"
                for key, value in failure_metrics.items():
                    mr_description += f"- **{key}**: {value}\n"

            mr_description += """
### Action Required
This is an **emergency rollback** MR. Please review and merge as soon as possible.

⚠️ **This rollback was automatically created by GUARD due to upgrade validation failures.**
"""

            logger.debug("creating_rollback_mr")
            mr = self.gitlab.create_merge_request(
                project_id=project_id,
                source_branch=branch_name,
                target_branch="main",
                title=mr_title,
                description=mr_description,
                draft=False,  # Rollback MRs should not be draft
            )

            # Extract web URL from MR object
            mr_url: str = mr.web_url

            logger.info(
                "rollback_mr_created_successfully",
                cluster_id=cluster.cluster_id,
                branch_name=branch_name,
                mr_url=mr_url,
            )

            return mr_url

        except Exception as e:
            logger.error(
                "rollback_mr_creation_failed",
                cluster_id=cluster.cluster_id,
                error=str(e),
            )
            raise
