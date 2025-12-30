"""Prometheus Query latency validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class PrometheusQueryLatencyValidator(Validator):
    """Validates Prometheus query engine latency after upgrade.

    Compares query latency metrics before and after upgrade to ensure
    performance hasn't degraded beyond acceptable thresholds.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "prometheus_query_latency"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Prometheus query engine latency (p95/p99) after upgrade"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate Prometheus query latency metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_prometheus_query_latency", cluster_id=cluster.cluster_id)

        violations = []

        # Check p95 query latency
        baseline_p95 = baseline.metrics.get("prometheus.query.latency.p95")
        current_p95 = current.metrics.get("prometheus.query.latency.p95")

        if baseline_p95 is None or current_p95 is None:
            violations.append("Query P95 latency metrics unavailable")
        elif baseline_p95 > 0:
            increase_percent = ((current_p95 - baseline_p95) / baseline_p95) * 100

            if increase_percent > thresholds.latency_p95_increase_percent:
                violations.append(
                    f"Query P95 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p95_increase_percent}%): "
                    f"{baseline_p95:.3f}s -> {current_p95:.3f}s"
                )

        # Check p99 query latency
        baseline_p99 = baseline.metrics.get("prometheus.query.latency.p99")
        current_p99 = current.metrics.get("prometheus.query.latency.p99")

        if baseline_p99 is None or current_p99 is None:
            violations.append("Query P99 latency metrics unavailable")
        elif baseline_p99 > 0:
            increase_percent = ((current_p99 - baseline_p99) / baseline_p99) * 100

            if increase_percent > thresholds.latency_p99_increase_percent:
                violations.append(
                    f"Query P99 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_p99_increase_percent}%): "
                    f"{baseline_p99:.3f}s -> {current_p99:.3f}s"
                )

        passed = len(violations) == 0

        logger.info(
            "prometheus_query_latency_validation_completed",
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
            "prometheus.query.latency.p95",
            "prometheus.query.latency.p99",
        ]
