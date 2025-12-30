"""Thanos Query latency validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ThanosQueryLatencyValidator(Validator):
    """Validates Thanos Query API latency after upgrade.

    Compares query latency metrics before and after upgrade to ensure
    performance hasn't degraded beyond acceptable thresholds.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "thanos_query_latency"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Thanos Query API latency (p95/p99) after upgrade"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate Thanos query latency metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_thanos_query_latency", cluster_id=cluster.cluster_id)

        violations = []

        # Check p95 instant query latency
        baseline_instant_p95 = baseline.metrics.get("thanos.query.api.instant.latency.p95")
        current_instant_p95 = current.metrics.get("thanos.query.api.instant.latency.p95")

        if baseline_instant_p95 is None or current_instant_p95 is None:
            violations.append("Instant query P95 latency metrics unavailable")
        elif baseline_instant_p95 > 0:
            increase_percent = (
                (current_instant_p95 - baseline_instant_p95) / baseline_instant_p95
            ) * 100

            if increase_percent > thresholds.latency_p95_increase_percent:
                violations.append(
                    f"Instant query P95 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p95_increase_percent}%): "
                    f"{baseline_instant_p95:.3f}s -> {current_instant_p95:.3f}s"
                )

        # Check p95 range query latency
        baseline_range_p95 = baseline.metrics.get("thanos.query.api.range.latency.p95")
        current_range_p95 = current.metrics.get("thanos.query.api.range.latency.p95")

        if baseline_range_p95 is None or current_range_p95 is None:
            violations.append("Range query P95 latency metrics unavailable")
        elif baseline_range_p95 > 0:
            increase_percent = ((current_range_p95 - baseline_range_p95) / baseline_range_p95) * 100

            if increase_percent > thresholds.latency_p95_increase_percent:
                violations.append(
                    f"Range query P95 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p95_increase_percent}%): "
                    f"{baseline_range_p95:.3f}s -> {current_range_p95:.3f}s"
                )

        passed = len(violations) == 0

        logger.info(
            "thanos_query_latency_validation_completed",
            cluster_id=cluster.cluster_id,
            passed=passed,
            violations=len(violations),
        )

        return ValidationResult(
            cluster_id=cluster.cluster_id,
            validator_name=self.name,
            passed=passed,
            violations=violations,
            metrics=current.metrics,
            timestamp=datetime.utcnow(),
        )

    async def get_required_metrics(self) -> list[str]:
        """Get required metric names.

        Returns:
            List of metric names
        """
        return [
            "thanos.query.api.instant.latency.p95",
            "thanos.query.api.range.latency.p95",
        ]
