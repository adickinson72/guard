"""Core data models for GUARD."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ClusterStatus(str, Enum):
    """Cluster status enum."""

    PENDING = "pending"
    PRE_CHECK_RUNNING = "pre-check-running"
    PRE_CHECK_PASSED = "pre-check-passed"
    PRE_CHECK_FAILED = "pre-check-failed"
    MR_CREATED = "mr-created"
    UPGRADING = "upgrading"
    POST_CHECK_RUNNING = "post-check-running"
    HEALTHY = "healthy"
    ROLLBACK_REQUIRED = "rollback-required"
    FAILED_UPGRADE_ROLLED_BACK = "failed-upgrade-rolled-back"


class UpgradeHistoryEntry(BaseModel):
    """Upgrade history entry."""

    version: str
    date: datetime
    status: str


class DatadogTags(BaseModel):
    """Datadog tags for a cluster."""

    cluster: str
    service: str = "istio-system"
    env: str


class ClusterMetadata(BaseModel):
    """Additional cluster metadata."""

    mesh_id: str | None = None
    multi_cluster: bool = False


class ClusterConfig(BaseModel):
    """Cluster configuration model."""

    cluster_id: str = Field(..., description="Unique cluster identifier")
    batch_id: str = Field(..., description="Batch identifier for upgrades")
    environment: str = Field(..., description="Environment: dev, staging, production")
    region: str = Field(..., description="AWS region")
    gitlab_repo: str = Field(..., description="GitLab repository path")
    flux_config_path: str = Field(..., description="Path to Flux config file in repo")
    aws_role_arn: str = Field(..., description="IAM role ARN for EKS access")
    current_istio_version: str = Field(..., description="Current Istio version")
    target_istio_version: str | None = Field(None, description="Target Istio version")
    datadog_tags: DatadogTags = Field(..., description="Datadog tags for metrics")
    owner_team: str = Field(..., description="Owner team name")
    owner_handle: str = Field(..., description="GitLab handle for MR assignment")
    status: ClusterStatus = Field(
        default=ClusterStatus.PENDING, description="Current cluster status"
    )
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    upgrade_history: list[UpgradeHistoryEntry] = Field(default_factory=list)
    metadata: ClusterMetadata = Field(default_factory=ClusterMetadata)

    class Config:
        """Pydantic config."""

        use_enum_values = True


class CheckResult(BaseModel):
    """Result of a health check."""

    check_name: str
    passed: bool
    message: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ValidationThresholds(BaseModel):
    """Validation thresholds for metrics comparison.

    Thresholds based on industry best practices for production Istio upgrades.
    All percentage values represent maximum acceptable increases from baseline.
    """

    # Latency thresholds (percentage increase from baseline)
    latency_p95_increase_percent: float = 10.0
    latency_p99_increase_percent: float = 15.0

    # Error rate thresholds
    error_rate_max: float = 0.001  # 0.1% absolute maximum
    error_rate_increase_max: float = 0.0005  # 0.05% relative increase from baseline

    # Resource thresholds (percentage increase from baseline)
    # Reduced from 50% to 25% based on consensus review
    resource_increase_percent: float = 25.0

    # Control plane specific thresholds
    istiod_resource_increase_percent: float = 30.0
    gateway_resource_increase_percent: float = 30.0

    # Request volume gating (minimum requests for valid comparison)
    min_request_volume: int = 1000

    # Pilot/control plane error thresholds
    pilot_xds_reject_threshold: int = 10  # Max rejected xDS pushes
    pilot_push_error_rate_max: float = 0.01  # 1% max push error rate


class FieldUpdate(BaseModel):
    """Specification for updating a field in the Flux HelmRelease config."""

    path: str = Field(..., description="Dotted path to field (e.g., 'spec.chart.spec.version')")
    value: Any = Field(..., description="Value to set at the specified path")

    @classmethod
    def validate_path(cls, path: str) -> bool:
        """Validate that path is non-empty and properly formatted.

        Args:
            path: Dotted path string

        Returns:
            True if valid

        Rejects:
            - Empty strings or non-strings
            - Paths with empty parts (e.g., "spec..version")
            - Paths with only whitespace in parts
            - Paths with consecutive dots
            - Paths starting or ending with dots
        """
        if not path or not isinstance(path, str):
            return False

        # Reject paths starting or ending with dots
        if path.startswith(".") or path.endswith("."):
            return False

        # Reject paths with consecutive dots
        if ".." in path:
            return False

        parts = path.split(".")

        # Ensure all parts are non-empty and not just whitespace
        return all(part and part.strip() == part and part.strip() for part in parts)


class UpgradeSpec(BaseModel):
    """Specification for an upgrade operation.

    This model defines which fields to update during an upgrade.
    Supports both JSON and YAML formats.
    """

    version: str = Field(..., description="Target version for the upgrade")
    updates: list[FieldUpdate] = Field(
        ...,
        description="List of field updates to apply",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_all_paths(self) -> "UpgradeSpec":
        """Validate all field update paths during deserialization.

        Returns:
            Self if validation passes

        Raises:
            ValueError: If any path is invalid
        """
        invalid_paths = [
            update.path for update in self.updates if not FieldUpdate.validate_path(update.path)
        ]

        if invalid_paths:
            raise ValueError(
                f"Invalid field paths in upgrade spec: {', '.join(invalid_paths)}. "
                f"Paths must not contain consecutive dots, leading/trailing dots, or empty parts."
            )

        return self

    def validate_updates(self) -> bool:
        """Validate all field updates have valid paths.

        Returns:
            True if all updates are valid

        Note:
            This method is deprecated in favor of the Pydantic model_validator.
            Path validation now happens automatically during deserialization.
        """
        return all(FieldUpdate.validate_path(update.path) for update in self.updates)
