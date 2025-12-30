"""Thanos Store availability validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ThanosStoreAvailabilityValidator(Validator):
    """Validates Thanos Store availability after upgrade.

    Checks that Store gateways are serving data and blocks are loaded.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "thanos_store_availability"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Thanos Store blocks are loaded and available"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate Thanos Store availability metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_thanos_store_availability", cluster_id=cluster.cluster_id)

        violations = []

        # Check blocks loaded
        baseline_blocks = baseline.metrics.get("thanos.store.blocks.loaded")
        current_blocks = current.metrics.get("thanos.store.blocks.loaded")

        if current_blocks is None:
            violations.append("Store blocks loaded metric unavailable")
        elif current_blocks < 1:
            violations.append(f"No blocks loaded in store (current: {current_blocks})")
        elif baseline_blocks is not None and baseline_blocks > 0:
            # Check if blocks decreased significantly (more than 20%)
            decrease_percent = ((baseline_blocks - current_blocks) / baseline_blocks) * 100
            if decrease_percent > 20:
                violations.append(
                    f"Store blocks decreased by {decrease_percent:.1f}%: "
                    f"{baseline_blocks:.0f} -> {current_blocks:.0f}"
                )

        # Check bucket store latency
        baseline_latency = baseline.metrics.get("thanos.store.bucket.latency.p95")
        current_latency = current.metrics.get("thanos.store.bucket.latency.p95")

        if baseline_latency is None or current_latency is None:
            # Latency metric is optional - warn but don't fail
            logger.warning(
                "thanos_store_latency_unavailable",
                cluster_id=cluster.cluster_id,
            )
        elif baseline_latency > 0:
            increase_percent = ((current_latency - baseline_latency) / baseline_latency) * 100
            if increase_percent > thresholds.latency_p95_increase_percent:
                violations.append(
                    f"Store bucket latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p95_increase_percent}%): "
                    f"{baseline_latency:.3f}s -> {current_latency:.3f}s"
                )

        passed = len(violations) == 0

        logger.info(
            "thanos_store_availability_validation_completed",
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
            "thanos.store.blocks.loaded",
            "thanos.store.bucket.latency.p95",
        ]
