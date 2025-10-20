"""Metrics comparator for pre/post upgrade comparison."""

from guard.core.models import ValidationThresholds
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class MetricsComparator:
    """Compare pre and post upgrade metrics.

    Implements comprehensive metric comparison logic based on industry best practices
    for Istio upgrade validation. Handles latency, error rates, resource usage, and
    control plane metrics.
    """

    def __init__(self, thresholds: ValidationThresholds):
        """Initialize metrics comparator.

        Args:
            thresholds: Validation thresholds
        """
        self.thresholds = thresholds
        logger.debug("metrics_comparator_initialized", thresholds=thresholds.model_dump())

    def _percent_change(self, baseline: float, current: float, floor: float = 1e-6) -> float:
        """Calculate percentage change from baseline to current.

        Args:
            baseline: Baseline value
            current: Current value
            floor: Minimum baseline value to avoid division by zero

        Returns:
            Percentage change
        """
        return ((current - baseline) / max(baseline, floor)) * 100.0

    def compare_metrics(
        self, baseline: dict[str, float | None], current: dict[str, float | None]
    ) -> tuple[bool, list[str]]:
        """Compare baseline and current metrics.

        Implements comprehensive validation logic including:
        - Latency degradation checks (p95, p99)
        - Error rate validation (absolute and relative)
        - Resource usage validation (general and component-specific)
        - Control plane health metrics (pilot xDS pushes)
        - Missing metric detection

        Args:
            baseline: Baseline metrics (may contain None for missing metrics)
            current: Current metrics (may contain None for missing metrics)

        Returns:
            Tuple of (passed, issues)
        """
        logger.info("comparing_metrics", baseline_count=len(baseline), current_count=len(current))
        issues = []

        # 1. Check for missing metrics (critical failure)
        missing_in_current = []
        for metric_name, baseline_value in baseline.items():
            current_value = current.get(metric_name)
            if current_value is None:
                missing_in_current.append(metric_name)
                issues.append(
                    f"CRITICAL: Metric '{metric_name}' is missing in current snapshot "
                    f"(baseline: {baseline_value})"
                )

        # 2. Latency checks (percentage increase from baseline)
        latency_metrics = {
            "istio.request.duration.p95": self.thresholds.latency_p95_increase_percent,
            "istio.request.duration.p99": self.thresholds.latency_p99_increase_percent,
            "http.latency.p95": self.thresholds.latency_p95_increase_percent,
            "http.latency.p99": self.thresholds.latency_p99_increase_percent,
        }

        for metric_name, threshold_percent in latency_metrics.items():
            if metric_name in baseline and metric_name in current:
                b_val = baseline[metric_name]
                c_val = current[metric_name]

                if b_val is not None and c_val is not None:
                    max_allowed = b_val * (1 + threshold_percent / 100)
                    if c_val > max_allowed:
                        pct_change = self._percent_change(b_val, c_val)
                        issues.append(
                            f"Latency degradation: {metric_name} increased {pct_change:.1f}% "
                            f"(baseline: {b_val:.2f}ms, current: {c_val:.2f}ms, "
                            f"threshold: {threshold_percent}%)"
                        )

        # 3. Error rate checks (absolute and relative)
        error_rate_metrics = [
            "istio.request.error_rate",
            "http.error_rate",
            "error.rate",
        ]

        for metric_name in error_rate_metrics:
            if metric_name in current:
                c_val = current[metric_name]
                b_val = baseline.get(metric_name)

                if c_val is not None:
                    # Check absolute maximum
                    if c_val > self.thresholds.error_rate_max:
                        issues.append(
                            f"Error rate too high: {metric_name} = {c_val:.4f} "
                            f"(max allowed: {self.thresholds.error_rate_max:.4f})"
                        )

                    # Check relative increase from baseline
                    if b_val is not None and c_val > (
                        b_val + self.thresholds.error_rate_increase_max
                    ):
                        issues.append(
                            f"Error rate increased: {metric_name} went from {b_val:.4f} "
                            f"to {c_val:.4f} (increase: {c_val - b_val:.4f}, "
                            f"max increase: {self.thresholds.error_rate_increase_max:.4f})"
                        )

        # 4. Resource usage checks (CPU, memory)
        resource_metrics = {
            # istiod-specific metrics
            "istiod.cpu": self.thresholds.istiod_resource_increase_percent,
            "istiod.memory": self.thresholds.istiod_resource_increase_percent,
            "istiod.cpu_usage": self.thresholds.istiod_resource_increase_percent,
            "istiod.mem_usage": self.thresholds.istiod_resource_increase_percent,
            # Gateway-specific metrics
            "gateway.cpu": self.thresholds.gateway_resource_increase_percent,
            "gateway.memory": self.thresholds.gateway_resource_increase_percent,
            "gateway.cpu_usage": self.thresholds.gateway_resource_increase_percent,
            "gateway.mem_usage": self.thresholds.gateway_resource_increase_percent,
            # General resource metrics
            "cpu.usage": self.thresholds.resource_increase_percent,
            "memory.usage": self.thresholds.resource_increase_percent,
        }

        for metric_name, threshold_percent in resource_metrics.items():
            if metric_name in baseline and metric_name in current:
                b_val = baseline[metric_name]
                c_val = current[metric_name]

                if b_val is not None and c_val is not None and b_val > 0:
                    pct_change = self._percent_change(b_val, c_val)
                    if pct_change > threshold_percent:
                        issues.append(
                            f"Resource usage increased: {metric_name} grew {pct_change:.1f}% "
                            f"(baseline: {b_val:.2f}, current: {c_val:.2f}, "
                            f"threshold: {threshold_percent}%)"
                        )

        # 5. Control plane metrics (pilot xDS)
        pilot_metrics = {
            "pilot_total_xds_rejects": ("reject", self.thresholds.pilot_xds_reject_threshold),
            "pilot.xds.rejects": ("reject", self.thresholds.pilot_xds_reject_threshold),
        }

        for metric_name, (metric_type, threshold) in pilot_metrics.items():
            if metric_name in current:
                c_val = current[metric_name]
                if c_val is not None and c_val > threshold:
                    issues.append(
                        f"Pilot xDS {metric_type}s too high: {metric_name} = {c_val:.0f} "
                        f"(max allowed: {threshold})"
                    )

        # 6. Request volume gating
        request_volume_metrics = [
            "istio.request.count",
            "http.request_count",
            "request.count",
        ]

        has_sufficient_volume = False
        for metric_name in request_volume_metrics:
            if metric_name in current:
                c_val = current[metric_name]
                if c_val is not None and c_val >= self.thresholds.min_request_volume:
                    has_sufficient_volume = True
                    break

        if not has_sufficient_volume:
            issues.append(
                f"WARNING: Insufficient request volume for meaningful comparison "
                f"(min required: {self.thresholds.min_request_volume}). "
                f"Consider extending soak period or validating during higher traffic."
            )

        passed = len(issues) == 0
        logger.info(
            "metrics_comparison_completed",
            passed=passed,
            issue_count=len(issues),
            missing_metrics_count=len(missing_in_current),
        )

        return passed, issues
