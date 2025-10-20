"""Istio error rate validator."""

from datetime import datetime

from guard.core.models import ClusterConfig, ValidationThresholds
from guard.interfaces.validator import MetricsSnapshot, ValidationResult, Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioErrorRateValidator(Validator):
    """Validates Istio error rates after upgrade.

    Checks that 5xx error rates haven't increased beyond
    acceptable thresholds after upgrade.
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "istio_error_rate"

    @property
    def description(self) -> str:
        """Get validator description."""
        return "Validates Istio 5xx error rates after upgrade"

    async def validate(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> ValidationResult:
        """Validate error rate metrics.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            ValidationResult with pass/fail and violations
        """
        logger.info("validating_istio_error_rate", cluster_id=cluster.cluster_id)

        violations = []

        # Check 5xx error rate
        baseline_errors = baseline.metrics.get("istio.request.error.5xx.rate", 0)
        current_errors = current.metrics.get("istio.request.error.5xx.rate", 0)

        # Check if error rate exceeds maximum
        if current_errors > thresholds.error_rate_max:
            violations.append(
                f"5xx error rate {current_errors:.4f} exceeds maximum "
                f"{thresholds.error_rate_max:.4f}"
            )

        # Check if error rate increased significantly
        if baseline_errors > 0:
            increase_ratio = current_errors / baseline_errors

            if increase_ratio > 2.0:  # More than 2x increase
                violations.append(
                    f"5xx error rate increased {increase_ratio:.1f}x: "
                    f"{baseline_errors:.4f} -> {current_errors:.4f}"
                )

        # Check total request count didn't drop significantly
        baseline_requests = baseline.metrics.get("istio.request.total.rate", 0)
        current_requests = current.metrics.get("istio.request.total.rate", 0)

        if baseline_requests > 0:
            drop_percent = ((baseline_requests - current_requests) / baseline_requests) * 100

            if drop_percent > 20:  # 20% drop threshold
                violations.append(
                    f"Request rate dropped {drop_percent:.1f}%: "
                    f"{baseline_requests:.0f} -> {current_requests:.0f} req/s"
                )

        passed = len(violations) == 0

        logger.info(
            "error_rate_validation_completed",
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
            "istio.request.error.5xx.rate",
            "istio.request.total.rate",
        ]
