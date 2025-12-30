"""Prometheus Scrape health validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusScrapeHealthValidator(Validator):
    """Validates Prometheus scrape target health after upgrade.

    Checks that scrape targets are being collected successfully and
    that the number of up targets hasn't decreased significantly.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "prometheus_scrape_health"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Prometheus scrape target availability after upgrade"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate Prometheus scrape health metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_prometheus_scrape_health", cluster_id=cluster.cluster_id)

        violations = []

        # Check targets up count
        baseline_targets_up = baseline.metrics.get("prometheus.scrape.targets.up")
        current_targets_up = current.metrics.get("prometheus.scrape.targets.up")

        if baseline_targets_up is None or current_targets_up is None:
            violations.append("Scrape targets up metrics unavailable")
        elif baseline_targets_up > 0:
            # Calculate decrease percentage (we care about targets going down)
            decrease_percent = (
                (baseline_targets_up - current_targets_up) / baseline_targets_up
            ) * 100

            # Allow up to 5% decrease in targets (some may be transient)
            target_decrease_threshold = 5.0
            if decrease_percent > target_decrease_threshold:
                violations.append(
                    f"Scrape targets up decreased {decrease_percent:.1f}% "
                    f"(threshold: {target_decrease_threshold}%): "
                    f"{baseline_targets_up:.0f} -> {current_targets_up:.0f}"
                )

        # Check scrape duration p95
        baseline_scrape_p95 = baseline.metrics.get("prometheus.scrape.duration.p95")
        current_scrape_p95 = current.metrics.get("prometheus.scrape.duration.p95")

        if (
            baseline_scrape_p95 is not None
            and current_scrape_p95 is not None
            and baseline_scrape_p95 > 0
        ):
            increase_percent = (
                (current_scrape_p95 - baseline_scrape_p95) / baseline_scrape_p95
            ) * 100

            # Use latency threshold for scrape duration
            if increase_percent > thresholds.latency_p95_increase_percent:
                violations.append(
                    f"Scrape duration P95 increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p95_increase_percent}%): "
                    f"{baseline_scrape_p95:.3f}s -> {current_scrape_p95:.3f}s"
                )

        passed = len(violations) == 0

        logger.info(
            "prometheus_scrape_health_validation_completed",
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
            "prometheus.scrape.targets.up",
            "prometheus.scrape.duration.p95",
        ]
