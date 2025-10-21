"""Validation orchestrator for post-upgrade validation."""

import asyncio
from datetime import datetime, timedelta

from guard.core.models import ClusterConfig, ValidationThresholds, get_metric_aggregation
from guard.interfaces.metrics_provider import MetricsProvider
from guard.interfaces.validator import MetricsSnapshot, ValidationResult
from guard.utils.logging import get_logger
from guard.validation.validator_registry import ValidatorRegistry

logger = get_logger(__name__)


class ValidationOrchestrator:
    """Orchestrates post-upgrade validation.

    This orchestrator coordinates validation execution without knowing
    the specifics of each validator. It handles:
    - Baseline metric capture
    - Current metric capture
    - Validator execution with timeouts
    - Result aggregation
    """

    def __init__(
        self,
        registry: ValidatorRegistry,
        metrics_provider: MetricsProvider,
        fail_fast: bool = False,
    ):
        """Initialize validation orchestrator.

        Args:
            registry: Validator registry
            metrics_provider: Metrics provider for querying metrics
            fail_fast: Stop on first validation failure (default: False)
        """
        self.registry = registry
        self.metrics = metrics_provider
        self.fail_fast = fail_fast
        logger.debug("validation_orchestrator_initialized", fail_fast=fail_fast)

    async def capture_baseline(
        self,
        cluster: ClusterConfig,
        duration_minutes: int = 10,
    ) -> MetricsSnapshot:
        """Capture baseline metrics before upgrade.

        Args:
            cluster: Cluster configuration
            duration_minutes: Duration to capture metrics over

        Returns:
            Metrics snapshot
        """
        logger.info(
            "capturing_baseline_metrics",
            cluster_id=cluster.cluster_id,
            duration=duration_minutes,
        )

        # Fix: Compute start_time from single end_time for consistency
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=duration_minutes)

        # Get all required metrics from validators
        validators = self.registry.get_validators(cluster)
        required_metrics = []
        for validator in validators:
            metrics = await validator.get_required_metrics()
            required_metrics.extend(metrics)

        # Remove duplicates
        required_metrics = list(set(required_metrics))

        # Query each metric
        metrics_data: dict[str, float | None] = {}
        failed_metrics = []
        tags = cluster.datadog_tags.model_dump()

        for metric_name in required_metrics:
            try:
                # Use per-metric aggregation instead of hardcoded "avg"
                aggregation = get_metric_aggregation(metric_name)
                value: float | None = await self.metrics.query_scalar(
                    metric_name=metric_name,
                    start_time=start_time,
                    end_time=end_time,
                    tags=tags,
                    aggregation=aggregation,
                )
                metrics_data[metric_name] = value
            except Exception as e:
                logger.error(
                    "metric_capture_failed",
                    metric_name=metric_name,
                    error=str(e),
                )
                # Fix: Store None instead of 0.0 to indicate missing data
                # This prevents masking monitoring failures
                metrics_data[metric_name] = None
                failed_metrics.append(metric_name)

        # Warn if metrics are missing
        if failed_metrics:
            logger.warning(
                "metrics_missing_in_baseline",
                cluster_id=cluster.cluster_id,
                failed_metrics=failed_metrics,
                failed_count=len(failed_metrics),
                total_count=len(required_metrics),
            )

        snapshot = MetricsSnapshot(
            timestamp=end_time,
            metrics=metrics_data,
            tags=tags,
        )

        logger.info(
            "baseline_captured",
            cluster_id=cluster.cluster_id,
            metric_count=len(metrics_data),
            missing_count=len(failed_metrics),
        )

        return snapshot

    async def capture_current(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        duration_minutes: int = 10,
    ) -> MetricsSnapshot:
        """Capture current metrics after upgrade.

        Args:
            cluster: Cluster configuration
            baseline: Baseline snapshot (to determine which metrics to query)
            duration_minutes: Duration to capture metrics over

        Returns:
            Metrics snapshot
        """
        logger.info(
            "capturing_current_metrics",
            cluster_id=cluster.cluster_id,
            duration=duration_minutes,
        )

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=duration_minutes)

        # Query same metrics as baseline
        metrics_data: dict[str, float | None] = {}
        failed_metrics = []
        tags = cluster.datadog_tags.model_dump()

        for metric_name in baseline.metrics:
            try:
                # Use per-metric aggregation instead of hardcoded "avg"
                aggregation = get_metric_aggregation(metric_name)
                value: float | None = await self.metrics.query_scalar(
                    metric_name=metric_name,
                    start_time=start_time,
                    end_time=end_time,
                    tags=tags,
                    aggregation=aggregation,
                )
                metrics_data[metric_name] = value
            except Exception as e:
                logger.error(
                    "metric_capture_failed",
                    metric_name=metric_name,
                    error=str(e),
                )
                # Fix: Store None instead of 0.0 to indicate missing data
                metrics_data[metric_name] = None
                failed_metrics.append(metric_name)

        # Warn if metrics are missing
        if failed_metrics:
            logger.warning(
                "metrics_missing_in_current",
                cluster_id=cluster.cluster_id,
                failed_metrics=failed_metrics,
                failed_count=len(failed_metrics),
                total_count=len(baseline.metrics),
            )

        snapshot = MetricsSnapshot(
            timestamp=end_time,
            metrics=metrics_data,
            tags=tags,
        )

        logger.info(
            "current_metrics_captured",
            cluster_id=cluster.cluster_id,
            metric_count=len(metrics_data),
            missing_count=len(failed_metrics),
        )

        return snapshot

    async def validate_upgrade(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
    ) -> list[ValidationResult]:
        """Run all validators to validate upgrade success.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds

        Returns:
            List of validation results
        """
        logger.info("validating_upgrade", cluster_id=cluster.cluster_id)

        validators = self.registry.get_validators(cluster)
        results = []

        for validator in validators:
            logger.debug("running_validator", validator_name=validator.name)

            try:
                result = await asyncio.wait_for(
                    validator.validate(cluster, baseline, current, thresholds),
                    timeout=validator.timeout_seconds,
                )
                results.append(result)

                logger.info(
                    "validator_completed",
                    validator_name=validator.name,
                    passed=result.passed,
                    violations=len(result.violations),
                )

                # Fail fast if enabled
                if self.fail_fast and not result.passed and validator.is_critical:
                    logger.warning(
                        "validator_failed_stopping",
                        validator_name=validator.name,
                    )
                    break

            except TimeoutError:
                logger.error(
                    "validator_timeout",
                    validator_name=validator.name,
                    timeout=validator.timeout_seconds,
                )

                result = ValidationResult(
                    cluster_id=cluster.cluster_id,
                    validator_name=validator.name,
                    passed=False,
                    violations=[f"Validator timed out after {validator.timeout_seconds}s"],
                    metrics={},
                    timestamp=datetime.utcnow(),
                )
                results.append(result)

                if self.fail_fast and validator.is_critical:
                    break

            except Exception as e:
                logger.error(
                    "validator_execution_failed",
                    validator_name=validator.name,
                    error=str(e),
                )

                result = ValidationResult(
                    cluster_id=cluster.cluster_id,
                    validator_name=validator.name,
                    passed=False,
                    violations=[f"Validator failed: {e}"],
                    metrics={},
                    timestamp=datetime.utcnow(),
                )
                results.append(result)

                if self.fail_fast and validator.is_critical:
                    break

        all_passed = all(r.passed for r in results)
        logger.info(
            "validation_completed",
            cluster_id=cluster.cluster_id,
            total=len(results),
            passed=sum(1 for r in results if r.passed),
            all_passed=all_passed,
        )

        return results

    async def run_specific_validators(
        self,
        cluster: ClusterConfig,
        baseline: MetricsSnapshot,
        current: MetricsSnapshot,
        thresholds: ValidationThresholds,
        validator_names: list[str],
    ) -> list[ValidationResult]:
        """Run specific named validators.

        Args:
            cluster: Cluster configuration
            baseline: Pre-upgrade metrics
            current: Post-upgrade metrics
            thresholds: Validation thresholds
            validator_names: Names of validators to run

        Returns:
            List of validation results
        """
        logger.info(
            "running_specific_validators",
            cluster_id=cluster.cluster_id,
            validator_names=validator_names,
        )

        results = []
        for validator_name in validator_names:
            validator = self.registry.get_validator(validator_name)
            if not validator:
                logger.warning("validator_not_found", validator_name=validator_name)
                continue

            try:
                result = await validator.validate(cluster, baseline, current, thresholds)
                results.append(result)
            except Exception as e:
                logger.error(
                    "validator_execution_failed",
                    validator_name=validator_name,
                    error=str(e),
                )

        return results
