"""GitOps orchestrator for managing upgrade merge requests."""

import tempfile
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from guard.core.models import ClusterConfig
from guard.interfaces.config_updater import ConfigUpdater
from guard.interfaces.exceptions import PartialFailureError
from guard.interfaces.gitops_provider import GitOpsProvider, MergeRequestInfo
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class GitOpsOrchestrator:
    """Orchestrates GitOps operations for upgrades.

    This orchestrator coordinates merge request creation without
    knowing file formats or service-specific details. It handles:
    - Branch creation
    - Configuration file updates (via ConfigUpdater)
    - Commit and MR creation
    """

    def __init__(
        self,
        git_provider: GitOpsProvider,
        config_updater: ConfigUpdater,
    ):
        """Initialize GitOps orchestrator.

        Args:
            git_provider: GitOps provider (GitLab, GitHub, etc.)
            config_updater: Config updater for specific format
        """
        self.git = git_provider
        self.updater = config_updater
        logger.debug("gitops_orchestrator_initialized")

    @staticmethod
    def group_clusters_by_repo_path(
        clusters: list[ClusterConfig],
    ) -> dict[tuple[str, str], list[ClusterConfig]]:
        """Group clusters by GitLab repo and flux path.

        Args:
            clusters: List of cluster configurations

        Returns:
            Dictionary mapping (gitlab_repo, flux_config_path) to list of clusters
        """
        grouped: dict[tuple[str, str], list[ClusterConfig]] = defaultdict(list)
        for cluster in clusters:
            key = (cluster.gitlab_repo, cluster.flux_config_path)
            grouped[key].append(cluster)

        logger.info(
            "clusters_grouped_by_repo_path",
            total_clusters=len(clusters),
            unique_repo_paths=len(grouped),
        )
        return dict(grouped)

    async def create_upgrade_mr(
        self,
        cluster: ClusterConfig,
        target_version: str,
        draft: bool = True,
        dry_run: bool = False,
    ) -> MergeRequestInfo:
        """Create an upgrade merge request.

        Args:
            cluster: Cluster configuration
            target_version: Target version for upgrade
            draft: Create as draft MR (default: True)
            dry_run: If True, only validate but don't create MR

        Returns:
            Merge request information

        Raises:
            GitOpsError: If MR creation fails
        """
        logger.info(
            "creating_upgrade_mr",
            cluster_id=cluster.cluster_id,
            target_version=target_version,
            dry_run=dry_run,
        )

        # Generate branch name
        branch_name = self._generate_branch_name(cluster, target_version)

        if dry_run:
            logger.info("dry_run_mode_no_mr_created", branch_name=branch_name)
            # Return placeholder MR info
            return MergeRequestInfo(
                id=0,
                iid=0,
                title=self._generate_mr_title(cluster, target_version),
                description=self._generate_mr_description(cluster, target_version),
                source_branch=branch_name,
                target_branch="main",
                state="draft",
                web_url="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        # Create branch (Option A: no pre-check, handle error if branch already exists)
        # The GitLab API will raise an error if the branch already exists,
        # which is the desired behavior to prevent race conditions.
        await self.git.create_branch(
            project_id=cluster.gitlab_repo,
            branch_name=branch_name,
            ref="main",
        )

        # Get current config file
        current_content = await self.git.get_file_content(
            project_id=cluster.gitlab_repo,
            file_path=cluster.flux_config_path,
            ref="main",
        )

        # Update version in config (save to temp file, then read)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                tmp.write(current_content)
                tmp_path = Path(tmp.name)

            # Update version
            await self.updater.update_version(tmp_path, target_version)

            # Read updated content
            with open(tmp_path) as f:
                updated_content = f.read()

        finally:
            # Clean up temp file (missing_ok handles race conditions)
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

        # Commit updated file
        commit_message = f"Upgrade to {target_version} for {cluster.cluster_id}"
        await self.git.update_file(
            project_id=cluster.gitlab_repo,
            file_path=cluster.flux_config_path,
            content=updated_content,
            commit_message=commit_message,
            branch=branch_name,
        )

        # Create merge request
        mr_title = self._generate_mr_title(cluster, target_version)
        mr_description = self._generate_mr_description(cluster, target_version)

        # Parse assignee from owner_handle if available
        assignee_ids = None
        if cluster.owner_handle:
            # Would need to look up user ID from handle
            # For now, skip assignee
            pass

        mr = await self.git.create_merge_request(
            project_id=cluster.gitlab_repo,
            source_branch=branch_name,
            target_branch="main",
            title=mr_title,
            description=mr_description,
            draft=draft,
            assignee_ids=assignee_ids,
        )

        logger.info(
            "upgrade_mr_created",
            cluster_id=cluster.cluster_id,
            mr_url=mr.web_url,
        )

        return mr

    async def create_upgrade_mrs_for_batch(
        self,
        clusters: list[ClusterConfig],
        target_version: str,
        draft: bool = True,
        dry_run: bool = False,
    ) -> dict[tuple[str, str], MergeRequestInfo]:
        """Create upgrade merge requests grouped by repo+path.

        Creates only ONE MR per unique (gitlab_repo, flux_config_path) combination,
        even if multiple clusters share the same repo and path.

        Args:
            clusters: List of cluster configurations
            target_version: Target version for upgrade
            draft: Create as draft MR (default: True)
            dry_run: If True, only validate but don't create MRs

        Returns:
            Dictionary mapping (gitlab_repo, flux_config_path) to MergeRequestInfo

        Raises:
            GitOpsError: If MR creation fails for any group
        """
        logger.info(
            "creating_batch_upgrade_mrs",
            total_clusters=len(clusters),
            target_version=target_version,
            dry_run=dry_run,
        )

        # Group clusters by repo+path
        grouped = self.group_clusters_by_repo_path(clusters)

        mr_infos: dict[tuple[str, str], MergeRequestInfo] = {}
        errors: list[str] = []
        failed_groups: list[tuple[str, str]] = []

        for (gitlab_repo, flux_path), cluster_group in grouped.items():
            try:
                # Determine batch_id (use first cluster's batch or combined batch)
                batch_ids = {c.batch_id for c in cluster_group}
                if len(batch_ids) == 1:
                    batch_id = batch_ids.pop()
                else:
                    # Multiple batches, use a combined name
                    batch_id = "-".join(sorted(batch_ids))

                cluster_ids = [c.cluster_id for c in cluster_group]

                logger.info(
                    "creating_mr_for_repo_path_group",
                    gitlab_repo=gitlab_repo,
                    flux_path=flux_path,
                    cluster_count=len(cluster_group),
                    cluster_ids=cluster_ids,
                )

                # Generate branch name with timestamp and UUID to avoid collisions
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                unique_id = str(uuid.uuid4())[:12]  # Use first 12 chars of UUID
                branch_name = f"upgrade/{batch_id}/{target_version}/{timestamp}-{unique_id}"

                if dry_run:
                    logger.info(
                        "dry_run_mode_no_mr_created_for_group",
                        gitlab_repo=gitlab_repo,
                        flux_path=flux_path,
                        branch_name=branch_name,
                    )
                    # Return placeholder MR info
                    mr_infos[(gitlab_repo, flux_path)] = MergeRequestInfo(
                        id=0,
                        iid=0,
                        title=self._generate_batch_mr_title(
                            batch_id, target_version, len(cluster_group)
                        ),
                        description=self._generate_batch_mr_description(
                            cluster_group, target_version, flux_path
                        ),
                        source_branch=branch_name,
                        target_branch="main",
                        state="draft",
                        web_url="",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    continue

                # Create branch
                await self.git.create_branch(
                    project_id=gitlab_repo,
                    branch_name=branch_name,
                    ref="main",
                )

                # Get current config file
                current_content = await self.git.get_file_content(
                    project_id=gitlab_repo,
                    file_path=flux_path,
                    ref="main",
                )

                # Update version in config
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                        tmp.write(current_content)
                        tmp_path = Path(tmp.name)

                    await self.updater.update_version(tmp_path, target_version)

                    with open(tmp_path) as f:
                        updated_content = f.read()
                finally:
                    if tmp_path:
                        tmp_path.unlink(missing_ok=True)

                # Commit updated file
                cluster_id_list = ", ".join(cluster_ids[:3])
                if len(cluster_ids) > 3:
                    cluster_id_list += f" and {len(cluster_ids) - 3} more"

                commit_message = f"Upgrade to {target_version} for {cluster_id_list}"
                await self.git.update_file(
                    project_id=gitlab_repo,
                    file_path=flux_path,
                    content=updated_content,
                    commit_message=commit_message,
                    branch=branch_name,
                )

                # Create merge request
                mr_title = self._generate_batch_mr_title(
                    batch_id, target_version, len(cluster_group)
                )
                mr_description = self._generate_batch_mr_description(
                    cluster_group, target_version, flux_path
                )

                mr = await self.git.create_merge_request(
                    project_id=gitlab_repo,
                    source_branch=branch_name,
                    target_branch="main",
                    title=mr_title,
                    description=mr_description,
                    draft=draft,
                )

                mr_infos[(gitlab_repo, flux_path)] = mr

                logger.info(
                    "upgrade_mr_created_for_group",
                    gitlab_repo=gitlab_repo,
                    flux_path=flux_path,
                    cluster_count=len(cluster_group),
                    mr_url=mr.web_url,
                )

            except Exception as e:
                error_msg = f"Failed to create MR for {gitlab_repo}:{flux_path}: {e}"
                logger.error(
                    "create_mr_for_group_failed",
                    gitlab_repo=gitlab_repo,
                    flux_path=flux_path,
                    error=str(e),
                )
                errors.append(error_msg)
                failed_groups.append((gitlab_repo, flux_path))

        # Raise exception if any MRs failed
        if errors:
            failed_count = len(errors)
            success_count = len(mr_infos)
            total_groups_count = len(grouped)

            logger.error(
                "batch_upgrade_mrs_partial_failure",
                total_mrs_created=success_count,
                total_groups=total_groups_count,
                failed_groups=failed_count,
                errors=errors,
            )

            # Build lists of successful and failed group identifiers
            successful_keys = [f"{repo}:{path}" for (repo, path) in mr_infos.keys()]
            failed_keys = [f"{repo}:{path}" for (repo, path) in failed_groups]

            raise PartialFailureError(
                message=f"Failed to create MRs for {failed_count}/{total_groups_count} groups. "
                f"{success_count} MRs created successfully.",
                successful_items=success_count,
                failed_items=failed_count,
                errors=errors,
                successful_keys=successful_keys,
                failed_keys=failed_keys,
            )

        logger.info(
            "batch_upgrade_mrs_created",
            total_mrs=len(mr_infos),
            total_clusters=len(clusters),
        )

        return mr_infos

    async def create_rollback_mr(
        self,
        cluster: ClusterConfig,
        rollback_version: str,
        reason: str,
    ) -> MergeRequestInfo:
        """Create a rollback merge request.

        Args:
            cluster: Cluster configuration
            rollback_version: Version to rollback to
            reason: Reason for rollback

        Returns:
            Merge request information

        Raises:
            GitOpsError: If MR creation fails
        """
        logger.info(
            "creating_rollback_mr",
            cluster_id=cluster.cluster_id,
            rollback_version=rollback_version,
        )

        # Generate branch name
        branch_name = f"rollback/{cluster.cluster_id}/{rollback_version}"

        # Create branch
        await self.git.create_branch(
            project_id=cluster.gitlab_repo,
            branch_name=branch_name,
            ref="main",
        )

        # Get and update config
        current_content = await self.git.get_file_content(
            project_id=cluster.gitlab_repo,
            file_path=cluster.flux_config_path,
            ref="main",
        )

        # Update version (same as upgrade, just different version)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                tmp.write(current_content)
                tmp_path = Path(tmp.name)

            await self.updater.update_version(tmp_path, rollback_version)

            with open(tmp_path) as f:
                updated_content = f.read()
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

        # Commit
        commit_message = (
            f"Rollback to {rollback_version} for {cluster.cluster_id}\n\nReason: {reason}"
        )
        await self.git.update_file(
            project_id=cluster.gitlab_repo,
            file_path=cluster.flux_config_path,
            content=updated_content,
            commit_message=commit_message,
            branch=branch_name,
        )

        # Create MR (not draft - emergency!)
        mr_title = f"[ROLLBACK] {cluster.cluster_id} to {rollback_version}"
        mr_description = f"# Rollback\n\n**Cluster**: {cluster.cluster_id}\n**Rollback to**: {rollback_version}\n**Reason**: {reason}"

        mr = await self.git.create_merge_request(
            project_id=cluster.gitlab_repo,
            source_branch=branch_name,
            target_branch="main",
            title=mr_title,
            description=mr_description,
            draft=False,  # Emergency rollback - not draft
        )

        logger.info(
            "rollback_mr_created",
            cluster_id=cluster.cluster_id,
            mr_url=mr.web_url,
        )

        return mr

    def _generate_branch_name(self, cluster: ClusterConfig, version: str) -> str:
        """Generate branch name for upgrade.

        Args:
            cluster: Cluster configuration
            version: Target version

        Returns:
            Branch name with timestamp and UUID to prevent collisions
        """
        # Remove any version prefixes (v1.20.0 -> 1.20.0)
        clean_version = version.lstrip("v")

        # Add timestamp and UUID to prevent collisions on retry
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:12]  # Use first 12 chars of UUID

        return f"upgrade/{cluster.cluster_id}/{clean_version}/{timestamp}-{unique_id}"

    def _generate_mr_title(self, cluster: ClusterConfig, version: str) -> str:
        """Generate MR title.

        Args:
            cluster: Cluster configuration
            version: Target version

        Returns:
            MR title
        """
        return f"Upgrade {cluster.cluster_id} to {version}"

    def _generate_mr_description(self, cluster: ClusterConfig, version: str) -> str:
        """Generate MR description.

        Args:
            cluster: Cluster configuration
            version: Target version

        Returns:
            MR description
        """
        return f"""# Upgrade

**Cluster**: {cluster.cluster_id}
**Environment**: {cluster.environment}
**Current Version**: {cluster.current_istio_version}
**Target Version**: {version}
**Batch**: {cluster.batch_id}
**Owner**: @{cluster.owner_handle}

## Pre-Checks

All pre-checks have passed for this cluster.

## Post-Merge

After merging, the upgrade will be applied via Flux.
Monitor the upgrade progress in Datadog.
"""

    def _generate_batch_mr_title(self, batch_id: str, version: str, cluster_count: int) -> str:
        """Generate MR title for batch upgrade.

        Args:
            batch_id: Batch identifier
            version: Target version
            cluster_count: Number of clusters in batch

        Returns:
            MR title
        """
        return f"Upgrade {batch_id} to {version} ({cluster_count} clusters)"

    def _generate_batch_mr_description(
        self, clusters: list[ClusterConfig], version: str, flux_path: str
    ) -> str:
        """Generate MR description for batch upgrade.

        Args:
            clusters: List of clusters in the batch
            version: Target version
            flux_path: Path to flux config file

        Returns:
            MR description
        """
        cluster_list = "\n".join([f"- {c.cluster_id}" for c in clusters])

        return f"""# Batch Upgrade

**Target Version**: {version}
**Flux Config Path**: `{flux_path}`

## Affected Clusters ({len(clusters)})

{cluster_list}

## Pre-Checks

All pre-checks have passed for these clusters.

## Post-Merge

After merging, the upgrade will be applied via Flux to all affected clusters.
Monitor the upgrade progress in Datadog.
"""
