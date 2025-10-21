"""Validator interface for post-upgrade validation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds


@dataclass
class MetricsSnapshot:
    """Snapshot of metrics at a point in time.

    Note: Metric values can be None to indicate missing/failed metric queries.
    This prevents masking monitoring failures by defaulting to 0.0.
    """

    timestamp: datetime
    metrics: dict[str, float | None]
    tags: dict[str, str]


@dataclass
class ValidationResult:
    """Result of a validation check."""

    cluster_id: str
    validator_name: str
    passed: bool
    violations: list[str]
    metrics: dict[str, float | None]
    timestamp: datetime


class Validator(ABC):
    """Abstract interface for post-upgrade validators.

    This interface defines the contract for validating upgrade success
    by comparing metrics before and after the upgrade.

    Design Philosophy:
    - Compares baseline (pre-upgrade) vs current (post-upgrade) metrics
    - Uses configurable thresholds
    - Returns specific violation messages
    - Service-specific implementations (Istio, Promtail, etc.)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the validator name for logging/reporting.

        Returns:
            Human-readable validator name
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Get a description of what this validator checks.

        Returns:
            Description of the validator's purpose
        """

    @abstractmethod
    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate upgrade success.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics snapshot
            current: Post-upgrade metrics snapshot
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations

        Raises:
            ValidationError: If validation execution fails
        """

    @abstractmethod
    async def get_required_metrics(self) -> list[str]:
        """Get list of metric names required by this validator.

        This allows the orchestrator to collect only necessary metrics.

        Returns:
            List of metric names (e.g., ["istio.request.latency.p95"])

        Raises:
            ValidationError: If metric list cannot be determined
        """

    @property
    def is_critical(self) -> bool:
        """Whether failure of this validator should trigger rollback.

        Returns:
            True if validator failure should trigger rollback (default: True)
        """
        return True

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time for this validator.

        Returns:
            Timeout in seconds (default: 60)
        """
        return 60
