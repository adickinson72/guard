"""Istio latency validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioLatencyValidator(Validator):
    """Validates Istio request latency after upgrade.

    Compares p95 latency before and after upgrade to ensure
    it hasn't degraded beyond acceptable thresholds.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "istio_latency"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Istio request latency (p95) after upgrade"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate latency metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_istio_latency", cluster_id=cluster.cluster_id)

        violations = []

        # Check p95 latency
        baseline_p95 = baseline.metrics.get("istio.request.latency.p95", 0)
        current_p95 = current.metrics.get("istio.request.latency.p95", 0)

        if baseline_p95 > 0:
            increase_percent = ((current_p95 - baseline_p95) / baseline_p95) * 100

            if increase_percent > thresholds.latency_increase_percent:
                violations.append(
                    f"P95 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_increase_percent}%): "
                    f"{baseline_p95:.2f}ms -> {current_p95:.2f}ms"
                )

        # Check p99 latency
        baseline_p99 = baseline.metrics.get("istio.request.latency.p99", 0)
        current_p99 = current.metrics.get("istio.request.latency.p99", 0)

        if baseline_p99 > 0:
            increase_percent = ((current_p99 - baseline_p99) / baseline_p99) * 100

            if increase_percent > thresholds.latency_increase_percent:
                violations.append(
                    f"P99 latency increased {increase_percent:.1f}% "
                    f"(threshold: {thresholds.latency_increase_percent}%): "
                    f"{baseline_p99:.2f}ms -> {current_p99:.2f}ms"
                )

        passed = len(violations) == 0

        logger.info(
            "latency_validation_completed",
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
            "istio.request.latency.p95",
            "istio.request.latency.p99",
        ]
