"""Unit tests for PreCheckEngine.

This module tests the legacy pre-check engine that orchestrates
synchronous health checks. Note: This is being phased out in favor
of the async CheckOrchestrator but is tested for backward compatibility.
"""

from unittest.mock import MagicMock

import pytest

from guard.checks.pre_check_engine import HealthCheck, PreCheckEngine
from guard.core.models import CheckResult, ClusterConfig


class MockHealthCheck(HealthCheck):
    """Mock health check implementation for testing."""

    def __init__(self, check_name: str, will_pass: bool = True, will_raise: Exception | None = None):
        """Initialize mock health check.

        Args:
            check_name: Name of the check for identification
            will_pass: Whether check will pass
            will_raise: Exception to raise during execution
        """
        self.check_name = check_name
        self._will_pass = will_pass
        self._will_raise = will_raise
        self.was_called = False

    def run(self, cluster: ClusterConfig) -> CheckResult:
        """Run the health check.

        Args:
            cluster: Cluster configuration

        Returns:
            CheckResult with pass/fail status

        Raises:
            Exception: If will_raise is set
        """
        self.was_called = True

        if self._will_raise:
            raise self._will_raise

        return CheckResult(
            check_name=self.check_name,
            passed=self._will_pass,
            message=f"{self.check_name} {'passed' if self._will_pass else 'failed'}",
            metrics={"test_metric": 1.0},
        )


@pytest.fixture
def passing_check() -> MockHealthCheck:
    """Provide a passing mock health check."""
    return MockHealthCheck("passing_check", will_pass=True)


@pytest.fixture
def failing_check() -> MockHealthCheck:
    """Provide a failing mock health check."""
    return MockHealthCheck("failing_check", will_pass=False)


@pytest.fixture
def exception_check() -> MockHealthCheck:
    """Provide a health check that raises an exception."""
    return MockHealthCheck(
        "exception_check",
        will_raise=RuntimeError("Check execution failed"),
    )


class TestHealthCheckBase:
    """Tests for HealthCheck base class."""

    def test_health_check_abstract_run_method(self) -> None:
        """Test that HealthCheck.run raises NotImplementedError by default."""
        check = HealthCheck()

        with pytest.raises(NotImplementedError, match="Subclasses must implement run"):
            check.run(MagicMock(spec=ClusterConfig))


class TestPreCheckEngineInitialization:
    """Tests for PreCheckEngine initialization."""

    def test_engine_initialization_empty(self) -> None:
        """Test initializing engine with no checks."""
        engine = PreCheckEngine(checks=[])

        assert engine.checks == []

    def test_engine_initialization_with_checks(
        self, passing_check: MockHealthCheck, failing_check: MockHealthCheck
    ) -> None:
        """Test initializing engine with checks."""
        engine = PreCheckEngine(checks=[passing_check, failing_check])

        assert len(engine.checks) == 2
        assert passing_check in engine.checks
        assert failing_check in engine.checks

    def test_engine_initialization_single_check(self, passing_check: MockHealthCheck) -> None:
        """Test initializing engine with single check."""
        engine = PreCheckEngine(checks=[passing_check])

        assert len(engine.checks) == 1
        assert engine.checks[0] == passing_check


class TestRunAllChecks:
    """Tests for run_all_checks method."""

    def test_run_all_checks_all_pass(
        self, sample_cluster_config: ClusterConfig, passing_check: MockHealthCheck
    ) -> None:
        """Test running checks when all pass."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=True)
        check3 = MockHealthCheck("check3", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2, check3])
        results = engine.run_all_checks(sample_cluster_config)

        assert len(results) == 3
        assert all(r.passed for r in results)
        assert check1.was_called
        assert check2.was_called
        assert check3.was_called

    def test_run_all_checks_stops_on_first_failure(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that engine stops on first check failure."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=False)
        check3 = MockHealthCheck("check3", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2, check3])
        results = engine.run_all_checks(sample_cluster_config)

        # Should stop after check2 fails
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

        # Verify execution stopped
        assert check1.was_called
        assert check2.was_called
        assert not check3.was_called  # Should not execute

    def test_run_all_checks_single_failure(
        self, sample_cluster_config: ClusterConfig, failing_check: MockHealthCheck
    ) -> None:
        """Test running a single failing check."""
        engine = PreCheckEngine(checks=[failing_check])
        results = engine.run_all_checks(sample_cluster_config)

        assert len(results) == 1
        assert results[0].passed is False
        assert failing_check.was_called

    def test_run_all_checks_empty_check_list(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test running checks with empty check list."""
        engine = PreCheckEngine(checks=[])
        results = engine.run_all_checks(sample_cluster_config)

        assert results == []

    def test_run_all_checks_result_order(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that results are returned in execution order."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=True)
        check3 = MockHealthCheck("check3", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2, check3])
        results = engine.run_all_checks(sample_cluster_config)

        assert results[0].check_name == "check1"
        assert results[1].check_name == "check2"
        assert results[2].check_name == "check3"

    def test_run_all_checks_result_messages(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that check result messages are properly set."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=False)

        engine = PreCheckEngine(checks=[check1, check2])
        results = engine.run_all_checks(sample_cluster_config)

        assert "passed" in results[0].message
        assert "failed" in results[1].message

    def test_run_all_checks_with_metrics(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that check results include metrics."""
        check1 = MockHealthCheck("check1", will_pass=True)

        engine = PreCheckEngine(checks=[check1])
        results = engine.run_all_checks(sample_cluster_config)

        assert len(results) == 1
        assert "test_metric" in results[0].metrics
        assert results[0].metrics["test_metric"] == 1.0


class TestExceptionHandling:
    """Tests for exception handling during check execution."""

    def test_run_all_checks_propagates_exceptions(
        self, sample_cluster_config: ClusterConfig, exception_check: MockHealthCheck
    ) -> None:
        """Test that exceptions from checks are propagated.

        Note: Current implementation doesn't catch exceptions,
        so they propagate to the caller. This is the expected behavior.
        """
        engine = PreCheckEngine(checks=[exception_check])

        with pytest.raises(RuntimeError, match="Check execution failed"):
            engine.run_all_checks(sample_cluster_config)

        assert exception_check.was_called

    def test_run_all_checks_exception_before_failure(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that exception stops execution like a failure would."""
        check1 = MockHealthCheck("check1", will_pass=True)
        exception_check = MockHealthCheck(
            "exception_check",
            will_raise=RuntimeError("Error"),
        )
        check3 = MockHealthCheck("check3", will_pass=True)

        engine = PreCheckEngine(checks=[check1, exception_check, check3])

        with pytest.raises(RuntimeError):
            engine.run_all_checks(sample_cluster_config)

        # First check should execute, third should not
        assert check1.was_called
        assert exception_check.was_called
        assert not check3.was_called


class TestCheckResultAggregation:
    """Tests for check result aggregation."""

    def test_run_all_checks_result_count_matches_executed(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that result count matches number of checks executed."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=False)
        check3 = MockHealthCheck("check3", will_pass=True)  # Won't execute

        engine = PreCheckEngine(checks=[check1, check2, check3])
        results = engine.run_all_checks(sample_cluster_config)

        # Only 2 checks executed (stopped after failure)
        assert len(results) == 2

    def test_run_all_checks_all_results_have_check_name(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that all results have check_name set."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2])
        results = engine.run_all_checks(sample_cluster_config)

        for result in results:
            assert result.check_name is not None
            assert isinstance(result.check_name, str)
            assert len(result.check_name) > 0

    def test_run_all_checks_all_results_have_timestamps(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test that all results have timestamps."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2])
        results = engine.run_all_checks(sample_cluster_config)

        for result in results:
            assert result.timestamp is not None


class TestIntegrationScenarios:
    """Integration tests for realistic check scenarios."""

    def test_realistic_pre_check_scenario(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test a realistic pre-check scenario with multiple checks."""
        # Simulate typical pre-checks: k8s, istio, datadog
        k8s_check = MockHealthCheck("kubernetes_health", will_pass=True)
        istio_check = MockHealthCheck("istio_health", will_pass=True)
        datadog_check = MockHealthCheck("datadog_alerts", will_pass=True)

        engine = PreCheckEngine(checks=[k8s_check, istio_check, datadog_check])
        results = engine.run_all_checks(sample_cluster_config)

        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_pre_check_fails_on_kubernetes_issue(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test pre-check stopping when Kubernetes check fails."""
        k8s_check = MockHealthCheck("kubernetes_health", will_pass=False)
        istio_check = MockHealthCheck("istio_health", will_pass=True)
        datadog_check = MockHealthCheck("datadog_alerts", will_pass=True)

        engine = PreCheckEngine(checks=[k8s_check, istio_check, datadog_check])
        results = engine.run_all_checks(sample_cluster_config)

        # Should stop after k8s check fails
        assert len(results) == 1
        assert results[0].passed is False
        assert k8s_check.was_called
        assert not istio_check.was_called
        assert not datadog_check.was_called

    def test_pre_check_partial_success(
        self, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test pre-check with some checks passing before failure."""
        check1 = MockHealthCheck("check1", will_pass=True)
        check2 = MockHealthCheck("check2", will_pass=True)
        check3 = MockHealthCheck("check3", will_pass=False)
        check4 = MockHealthCheck("check4", will_pass=True)

        engine = PreCheckEngine(checks=[check1, check2, check3, check4])
        results = engine.run_all_checks(sample_cluster_config)

        assert len(results) == 3
        assert results[0].passed is True
        assert results[1].passed is True
        assert results[2].passed is False
        assert not check4.was_called
