"""Unit tests for CheckOrchestrator.

This module tests the check orchestration logic that coordinates
execution of multiple health checks with timeouts, failure isolation,
and result aggregation.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from guard.checks.check_orchestrator import CheckOrchestrator
from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext


class MockCheck(Check):
    """Mock check implementation for testing."""

    def __init__(
        self,
        check_name: str,
        check_description: str,
        will_pass: bool = True,
        execution_delay: float = 0.0,
        will_raise: Exception | None = None,
        is_critical_check: bool = True,
        timeout: int = 60,
    ):
        """Initialize mock check.

        Args:
            check_name: Name of the check
            check_description: Description of the check
            will_pass: Whether check will pass
            execution_delay: Delay before returning result (seconds)
            will_raise: Exception to raise during execution
            is_critical_check: Whether check is critical
            timeout: Check timeout in seconds
        """
        self._name = check_name
        self._description = check_description
        self._will_pass = will_pass
        self._execution_delay = execution_delay
        self._will_raise = will_raise
        self._is_critical = is_critical_check
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Get check name."""
        return self._name

    @property
    def description(self) -> str:
        """Get check description."""
        return self._description

    @property
    def is_critical(self) -> bool:
        """Whether this is a critical check."""
        return self._is_critical

    @property
    def timeout_seconds(self) -> int:
        """Maximum execution time for this check."""
        return self._timeout

    async def execute(self, cluster: ClusterConfig, context: CheckContext) -> CheckResult:
        """Execute the health check."""
        # Simulate execution delay
        if self._execution_delay > 0:
            await asyncio.sleep(self._execution_delay)

        # Simulate exception
        if self._will_raise:
            raise self._will_raise

        # Return result
        return CheckResult(
            check_name=self.name,
            passed=self._will_pass,
            message=f"Check {'passed' if self._will_pass else 'failed'}",
            metrics={"test_metric": 1.0},
        )


@pytest.fixture
def registry() -> CheckRegistry:
    """Provide a check registry."""
    return CheckRegistry()


@pytest.fixture
def mock_context() -> CheckContext:
    """Provide a mock check context."""
    return CheckContext(
        cloud_provider=MagicMock(),
        kubernetes_provider=MagicMock(),
        metrics_provider=MagicMock(),
        extra_context={},
    )


class TestCheckOrchestratorInitialization:
    """Tests for CheckOrchestrator initialization."""

    def test_orchestrator_initialization_defaults(self, registry: CheckRegistry) -> None:
        """Test orchestrator initializes with default values."""
        orchestrator = CheckOrchestrator(registry)

        assert orchestrator.registry == registry
        assert orchestrator.fail_fast is True
        assert orchestrator.max_concurrent == 5

    def test_orchestrator_initialization_custom_values(self, registry: CheckRegistry) -> None:
        """Test orchestrator initialization with custom values."""
        orchestrator = CheckOrchestrator(
            registry=registry,
            fail_fast=False,
            max_concurrent=10,
        )

        assert orchestrator.registry == registry
        assert orchestrator.fail_fast is False
        assert orchestrator.max_concurrent == 10


class TestRunChecks:
    """Tests for run_checks method."""

    @pytest.mark.asyncio
    async def test_run_checks_all_pass(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running checks when all pass."""
        check1 = MockCheck("check1", "First check", will_pass=True)
        check2 = MockCheck("check2", "Second check", will_pass=True)

        registry.register(check1)
        registry.register(check2)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        assert len(results) == 2
        assert all(r.passed for r in results)
        assert results[0].check_name == "check1"
        assert results[1].check_name == "check2"

    @pytest.mark.asyncio
    async def test_run_checks_fail_fast_on_failure(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that fail_fast stops on first critical failure."""
        check1 = MockCheck("check1", "First check", will_pass=True)
        check2 = MockCheck("check2", "Second check", will_pass=False, is_critical_check=True)
        check3 = MockCheck("check3", "Third check", will_pass=True)

        registry.register(check1)
        registry.register(check2)
        registry.register(check3)

        orchestrator = CheckOrchestrator(registry, fail_fast=True)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        # Should stop after check2 fails
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False
        # check3 should not be executed

    @pytest.mark.asyncio
    async def test_run_checks_continue_on_non_critical_failure(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that non-critical failures don't stop execution."""
        check1 = MockCheck("check1", "First check", will_pass=True)
        check2 = MockCheck("check2", "Second check", will_pass=False, is_critical_check=False)
        check3 = MockCheck("check3", "Third check", will_pass=True)

        registry.register(check1)
        registry.register(check2)
        registry.register(check3)

        orchestrator = CheckOrchestrator(registry, fail_fast=True)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        # Should continue since check2 is non-critical
        assert len(results) == 3
        assert results[0].passed is True
        assert results[1].passed is False
        assert results[2].passed is True

    @pytest.mark.asyncio
    async def test_run_checks_no_fail_fast(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running all checks when fail_fast is disabled."""
        check1 = MockCheck("check1", "First check", will_pass=False)
        check2 = MockCheck("check2", "Second check", will_pass=False)
        check3 = MockCheck("check3", "Third check", will_pass=True)

        registry.register(check1)
        registry.register(check2)
        registry.register(check3)

        orchestrator = CheckOrchestrator(registry, fail_fast=False)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        # All checks should run
        assert len(results) == 3
        assert results[0].passed is False
        assert results[1].passed is False
        assert results[2].passed is True

    @pytest.mark.asyncio
    async def test_run_checks_handles_timeout(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check timeout is handled correctly."""
        # Create check with short timeout and longer execution delay
        slow_check = MockCheck(
            "slow_check",
            "Slow check",
            execution_delay=2.0,
            timeout=1,  # 1 second timeout
        )

        registry.register(slow_check)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        assert len(results) == 1
        assert results[0].passed is False
        assert "timed out" in results[0].message.lower()

    @pytest.mark.asyncio
    async def test_run_checks_handles_exception(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that check exceptions are caught and reported."""
        failing_check = MockCheck(
            "failing_check",
            "Failing check",
            will_raise=RuntimeError("Check execution failed"),
        )

        registry.register(failing_check)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        assert len(results) == 1
        assert results[0].passed is False
        assert "Check execution failed" in results[0].message

    @pytest.mark.asyncio
    async def test_run_checks_empty_registry(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running checks with empty registry."""
        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        assert results == []


class TestRunSpecificChecks:
    """Tests for run_specific_checks method."""

    @pytest.mark.asyncio
    async def test_run_specific_checks_by_name(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running specific checks by name."""
        check1 = MockCheck("check1", "First check", will_pass=True)
        check2 = MockCheck("check2", "Second check", will_pass=True)
        check3 = MockCheck("check3", "Third check", will_pass=True)

        registry.register(check1)
        registry.register(check2)
        registry.register(check3)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_specific_checks(
            sample_cluster_config,
            mock_context,
            check_names=["check1", "check3"],
        )

        assert len(results) == 2
        assert results[0].check_name == "check1"
        assert results[1].check_name == "check3"

    @pytest.mark.asyncio
    async def test_run_specific_checks_not_found(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running specific checks when some don't exist."""
        check1 = MockCheck("check1", "First check", will_pass=True)
        registry.register(check1)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_specific_checks(
            sample_cluster_config,
            mock_context,
            check_names=["check1", "nonexistent"],
        )

        # Only check1 should run
        assert len(results) == 1
        assert results[0].check_name == "check1"

    @pytest.mark.asyncio
    async def test_run_specific_checks_handles_exception(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that exceptions in specific checks are handled."""
        failing_check = MockCheck(
            "failing_check",
            "Failing check",
            will_raise=RuntimeError("Test error"),
        )
        registry.register(failing_check)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_specific_checks(
            sample_cluster_config,
            mock_context,
            check_names=["failing_check"],
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert "Test error" in results[0].message


class TestRunCriticalChecksOnly:
    """Tests for run_critical_checks_only method."""

    @pytest.mark.asyncio
    async def test_run_critical_checks_only(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running only critical checks."""
        critical1 = MockCheck("critical1", "Critical check 1", is_critical_check=True)
        non_critical = MockCheck("non_critical", "Non-critical check", is_critical_check=False)
        critical2 = MockCheck("critical2", "Critical check 2", is_critical_check=True)

        registry.register(critical1)
        registry.register(non_critical)
        registry.register(critical2)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_critical_checks_only(sample_cluster_config, mock_context)

        # Only critical checks should run
        assert len(results) == 2
        check_names = [r.check_name for r in results]
        assert "critical1" in check_names
        assert "critical2" in check_names
        assert "non_critical" not in check_names

    @pytest.mark.asyncio
    async def test_run_critical_checks_fail_fast(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that critical checks stop on first failure when fail_fast enabled."""
        critical1 = MockCheck("critical1", "Critical 1", will_pass=True, is_critical_check=True)
        critical2 = MockCheck("critical2", "Critical 2", will_pass=False, is_critical_check=True)
        critical3 = MockCheck("critical3", "Critical 3", will_pass=True, is_critical_check=True)

        registry.register(critical1)
        registry.register(critical2)
        registry.register(critical3)

        orchestrator = CheckOrchestrator(registry, fail_fast=True)
        results = await orchestrator.run_critical_checks_only(sample_cluster_config, mock_context)

        # Should stop after critical2 fails
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    @pytest.mark.asyncio
    async def test_run_critical_checks_handles_exception(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that exceptions in critical checks are handled."""
        failing_critical = MockCheck(
            "failing_critical",
            "Failing critical check",
            will_raise=RuntimeError("Critical failure"),
            is_critical_check=True,
        )
        registry.register(failing_critical)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_critical_checks_only(sample_cluster_config, mock_context)

        assert len(results) == 1
        assert results[0].passed is False
        assert "Critical failure" in results[0].message

    @pytest.mark.asyncio
    async def test_run_critical_checks_no_critical_checks(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test running critical checks when none are registered."""
        non_critical = MockCheck("non_critical", "Non-critical", is_critical_check=False)
        registry.register(non_critical)

        orchestrator = CheckOrchestrator(registry)
        results = await orchestrator.run_critical_checks_only(sample_cluster_config, mock_context)

        assert results == []


class TestResultAggregation:
    """Tests for result aggregation and logging."""

    @pytest.mark.asyncio
    async def test_result_aggregation_mixed_results(
        self,
        registry: CheckRegistry,
        sample_cluster_config: ClusterConfig,
        mock_context: CheckContext,
    ) -> None:
        """Test that results are properly aggregated."""
        check1 = MockCheck("check1", "Check 1", will_pass=True)
        check2 = MockCheck("check2", "Check 2", will_pass=False, is_critical_check=False)
        check3 = MockCheck("check3", "Check 3", will_pass=True)

        registry.register(check1)
        registry.register(check2)
        registry.register(check3)

        orchestrator = CheckOrchestrator(registry, fail_fast=False)
        results = await orchestrator.run_checks(sample_cluster_config, mock_context)

        assert len(results) == 3
        passed_count = sum(1 for r in results if r.passed)
        failed_count = sum(1 for r in results if not r.passed)

        assert passed_count == 2
        assert failed_count == 1
