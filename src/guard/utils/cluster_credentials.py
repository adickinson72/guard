"""Cluster credential management with expiration tracking and refresh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.adapters.aws_adapter import AWSAdapter
    from guard.clients.aws_client import AWSClient
    from guard.core.models import ClusterConfig
    from guard.utils.kubeconfig import KubeconfigManager

logger = get_logger(__name__)


@dataclass
class ClusterCredentials:
    """Credentials for a cluster with expiration tracking."""

    cluster_id: str
    aws_client: AWSClient
    created_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        """Check if credentials are expired or close to expiry.

        Returns True if credentials expire within 5 minutes to allow for refresh time.
        """
        buffer = timedelta(minutes=5)
        return datetime.utcnow() + buffer >= self.expires_at

    def time_until_expiry(self) -> timedelta:
        """Get time remaining until credentials expire."""
        return self.expires_at - datetime.utcnow()


class ClusterCredentialManager:
    """Manages cluster credentials with automatic refresh on expiration.

    This manager handles:
    - AssumeRole credential caching and refresh (1 hour expiry)
    - EKS token generation just-in-time (60 second expiry)
    - Kubeconfig context management

    Credentials are cached per cluster and refreshed automatically when they approach expiry.
    EKS tokens are generated on-demand and not cached (too short-lived).
    """

    def __init__(
        self,
        aws_adapter: AWSAdapter,
        kubeconfig_manager: KubeconfigManager,
    ):
        """Initialize credential manager.

        Args:
            aws_adapter: AWS adapter for assuming roles
            kubeconfig_manager: Kubeconfig manager for context generation
        """
        self.aws_adapter = aws_adapter
        self.kubeconfig_manager = kubeconfig_manager
        self._credentials_cache: dict[str, ClusterCredentials] = {}
        logger.debug("cluster_credential_manager_initialized")

    def _create_credentials(
        self, cluster: ClusterConfig, region: str | None = None
    ) -> ClusterCredentials:
        """Create fresh credentials for a cluster.

        Args:
            cluster: Cluster configuration
            region: AWS region (uses cluster region if None)

        Returns:
            ClusterCredentials with assumed role client
        """
        logger.info("creating_cluster_credentials", cluster_id=cluster.cluster_id)

        target_region = region or cluster.region

        # Create AWS client with assumed role
        # AssumeRole returns credentials valid for 1 hour (3600 seconds)
        cluster_aws_client = self.aws_adapter.create_client_for_cluster(
            role_arn=cluster.aws_role_arn,
            region=target_region,
            session_name=f"GUARD-{cluster.cluster_id}",
        )

        created_at = datetime.utcnow()
        # AssumeRole credentials expire after 1 hour, but refresh 5 mins early
        expires_at = created_at + timedelta(minutes=55)

        credentials = ClusterCredentials(
            cluster_id=cluster.cluster_id,
            aws_client=cluster_aws_client,
            created_at=created_at,
            expires_at=expires_at,
        )

        logger.info(
            "cluster_credentials_created",
            cluster_id=cluster.cluster_id,
            expires_in_minutes=credentials.time_until_expiry().total_seconds() / 60,
        )

        return credentials

    def get_credentials(
        self, cluster: ClusterConfig, region: str | None = None
    ) -> ClusterCredentials:
        """Get credentials for a cluster, creating or refreshing as needed.

        Args:
            cluster: Cluster configuration
            region: AWS region (uses cluster region if None)

        Returns:
            ClusterCredentials that are fresh and not expired
        """
        cached = self._credentials_cache.get(cluster.cluster_id)

        # Create new credentials if none cached or if expired
        if cached is None or cached.is_expired():
            if cached and cached.is_expired():
                logger.info(
                    "refreshing_expired_credentials",
                    cluster_id=cluster.cluster_id,
                    time_until_expiry_seconds=cached.time_until_expiry().total_seconds(),
                )

            credentials = self._create_credentials(cluster, region)
            self._credentials_cache[cluster.cluster_id] = credentials
            return credentials

        logger.debug(
            "using_cached_credentials",
            cluster_id=cluster.cluster_id,
            time_until_expiry_minutes=cached.time_until_expiry().total_seconds() / 60,
        )
        return cached

    def setup_kubeconfig_context(self, cluster: ClusterConfig) -> str:
        """Setup kubeconfig context for a cluster with fresh credentials and token.

        This method:
        1. Gets or refreshes AssumeRole credentials (1 hour expiry)
        2. Generates fresh EKS token (60 second expiry) - NOT cached
        3. Updates kubeconfig with new context

        Args:
            cluster: Cluster configuration

        Returns:
            Path to kubeconfig file
        """
        logger.info(
            "setting_up_kubeconfig_context",
            cluster_id=cluster.cluster_id,
        )

        # Get fresh credentials (auto-refreshes if expired)
        credentials = self.get_credentials(cluster)

        # Generate fresh EKS token (expires in 60 seconds, so never cache)
        # This ensures token is always fresh when K8s operations occur
        logger.debug(
            "generating_fresh_eks_token",
            cluster_id=cluster.cluster_id,
        )
        token_data = credentials.aws_client.generate_kubeconfig_token(cluster.cluster_id)

        # Add/update context in kubeconfig
        self.kubeconfig_manager.add_eks_cluster_context(
            context_name=cluster.cluster_id,
            cluster_name=cluster.cluster_id,
            endpoint=token_data["endpoint"],
            ca_data=token_data["ca_data"],
            token=token_data["token"],
            region=cluster.region,
        )

        logger.info(
            "kubeconfig_context_ready",
            cluster_id=cluster.cluster_id,
            kubeconfig_path=self.kubeconfig_manager.get_kubeconfig_path(),
        )

        return self.kubeconfig_manager.get_kubeconfig_path()

    def clear_credentials(self, cluster_id: str) -> None:
        """Clear cached credentials for a cluster.

        Args:
            cluster_id: Cluster ID to clear
        """
        if cluster_id in self._credentials_cache:
            del self._credentials_cache[cluster_id]
            logger.debug("credentials_cleared", cluster_id=cluster_id)

    def clear_all_credentials(self) -> None:
        """Clear all cached credentials."""
        count = len(self._credentials_cache)
        self._credentials_cache.clear()
        logger.info("all_credentials_cleared", count=count)
