"""Unit tests for CheckRegistry.

This module tests the health check registry that stores and manages
health checks for execution. Tests cover registration, retrieval,
filtering, and error cases.
"""

from unittest.mock import MagicMock

import pytest

from guard.checks.check_registry import CheckRegistry
from guard.core.models import CheckResult, ClusterConfig
from guard.interfaces.check import Check, CheckContext


class MockCheck(Check):
    """Mock check implementation for testing."""

    def __init__(
        self,
        check_name: str,
        check_description: str,
        is_critical_check: bool = True,
        timeout: int = 60,
    ):
        """Initialize mock check.

        Args:
            check_name: Name of the check
            check_description: Description of the check
            is_critical_check: Whether check is critical
            timeout: Check timeout in seconds
        """
        self._name = check_name
        self._description = check_description
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
        return CheckResult(
            check_name=self.name,
            passed=True,
            message="Mock check passed",
            metrics={},
        )


@pytest.fixture
def registry() -> CheckRegistry:
    """Provide a fresh check registry."""
    return CheckRegistry()


@pytest.fixture
def sample_check() -> MockCheck:
    """Provide a sample mock check."""
    return MockCheck(
        check_name="sample_check",
        check_description="A sample check for testing",
        is_critical_check=True,
    )


@pytest.fixture
def non_critical_check() -> MockCheck:
    """Provide a non-critical mock check."""
    return MockCheck(
        check_name="non_critical_check",
        check_description="A non-critical check",
        is_critical_check=False,
    )


class TestCheckRegistryInitialization:
    """Tests for CheckRegistry initialization."""

    def test_registry_initialization(self, registry: CheckRegistry) -> None:
        """Test that registry initializes with empty state."""
        assert len(registry) == 0
        assert registry.get_all_checks() == []

    def test_registry_internal_structures_initialized(self, registry: CheckRegistry) -> None:
        """Test that internal data structures are initialized correctly."""
        assert registry._checks == []
        assert registry._checks_by_name == {}


class TestCheckRegistration:
    """Tests for check registration."""

    def test_register_single_check(self, registry: CheckRegistry, sample_check: MockCheck) -> None:
        """Test registering a single check."""
        registry.register(sample_check)

        assert len(registry) == 1
        assert sample_check in registry.get_all_checks()

    def test_register_multiple_checks(
        self, registry: CheckRegistry, sample_check: MockCheck, non_critical_check: MockCheck
    ) -> None:
        """Test registering multiple checks."""
        registry.register(sample_check)
        registry.register(non_critical_check)

        assert len(registry) == 2
        all_checks = registry.get_all_checks()
        assert sample_check in all_checks
        assert non_critical_check in all_checks

    def test_register_duplicate_check_name_does_not_duplicate(
        self, registry: CheckRegistry, sample_check: MockCheck
    ) -> None:
        """Test that registering the same check name twice does not create duplicates."""
        registry.register(sample_check)
        registry.register(sample_check)  # Register again

        assert len(registry) == 1  # Should still be 1

    def test_register_different_checks_with_same_name(self, registry: CheckRegistry) -> None:
        """Test that checks with the same name don't create duplicates."""
        check1 = MockCheck("duplicate_name", "First check")
        check2 = MockCheck("duplicate_name", "Second check")

        registry.register(check1)
        registry.register(check2)  # Should not add second check

        assert len(registry) == 1
        # First registered check should be kept
        assert registry.get_check("duplicate_name") == check1


class TestCheckRetrieval:
    """Tests for check retrieval."""

    def test_get_check_by_name(self, registry: CheckRegistry, sample_check: MockCheck) -> None:
        """Test retrieving a check by name."""
        registry.register(sample_check)

        retrieved = registry.get_check("sample_check")
        assert retrieved is sample_check

    def test_get_check_not_found_returns_none(self, registry: CheckRegistry) -> None:
        """Test that getting a non-existent check returns None."""
        result = registry.get_check("nonexistent_check")
        assert result is None

    def test_get_all_checks_returns_copy(
        self, registry: CheckRegistry, sample_check: MockCheck
    ) -> None:
        """Test that get_all_checks returns a copy, not the internal list."""
        registry.register(sample_check)

        checks1 = registry.get_all_checks()
        checks2 = registry.get_all_checks()

        # Should be equal but not the same object
        assert checks1 == checks2
        assert checks1 is not checks2

    def test_get_all_checks_empty_registry(self, registry: CheckRegistry) -> None:
        """Test getting all checks from empty registry."""
        checks = registry.get_all_checks()
        assert checks == []
        assert isinstance(checks, list)


class TestCheckUnregistration:
    """Tests for check unregistration."""

    def test_unregister_existing_check(
        self, registry: CheckRegistry, sample_check: MockCheck
    ) -> None:
        """Test unregistering an existing check."""
        registry.register(sample_check)
        assert len(registry) == 1

        result = registry.unregister("sample_check")

        assert result is True
        assert len(registry) == 0
        assert registry.get_check("sample_check") is None

    def test_unregister_nonexistent_check_returns_false(self, registry: CheckRegistry) -> None:
        """Test that unregistering a non-existent check returns False."""
        result = registry.unregister("nonexistent_check")
        assert result is False

    def test_unregister_removes_from_both_structures(
        self, registry: CheckRegistry, sample_check: MockCheck
    ) -> None:
        """Test that unregister removes from both internal structures."""
        registry.register(sample_check)

        registry.unregister("sample_check")

        # Check both internal structures are updated
        assert sample_check not in registry._checks
        assert "sample_check" not in registry._checks_by_name


class TestCriticalCheckFiltering:
    """Tests for critical check filtering."""

    def test_get_critical_checks_only(
        self, registry: CheckRegistry, sample_check: MockCheck, non_critical_check: MockCheck
    ) -> None:
        """Test getting only critical checks."""
        registry.register(sample_check)
        registry.register(non_critical_check)

        critical_checks = registry.get_critical_checks()

        assert len(critical_checks) == 1
        assert sample_check in critical_checks
        assert non_critical_check not in critical_checks

    def test_get_critical_checks_empty_when_none_registered(
        self, registry: CheckRegistry, non_critical_check: MockCheck
    ) -> None:
        """Test getting critical checks when only non-critical checks exist."""
        registry.register(non_critical_check)

        critical_checks = registry.get_critical_checks()
        assert critical_checks == []

    def test_get_critical_checks_all_when_all_critical(
        self, registry: CheckRegistry
    ) -> None:
        """Test getting critical checks when all checks are critical."""
        check1 = MockCheck("critical1", "First critical", is_critical_check=True)
        check2 = MockCheck("critical2", "Second critical", is_critical_check=True)

        registry.register(check1)
        registry.register(check2)

        critical_checks = registry.get_critical_checks()

        assert len(critical_checks) == 2
        assert check1 in critical_checks
        assert check2 in critical_checks


class TestClusterSpecificChecks:
    """Tests for cluster-specific check retrieval."""

    def test_get_checks_for_cluster_returns_all(
        self,
        registry: CheckRegistry,
        sample_check: MockCheck,
        non_critical_check: MockCheck,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test that get_checks_for_cluster currently returns all checks."""
        registry.register(sample_check)
        registry.register(non_critical_check)

        checks = registry.get_checks_for_cluster(sample_cluster_config)

        # Current implementation returns all checks
        assert len(checks) == 2
        assert sample_check in checks
        assert non_critical_check in checks

    def test_get_checks_for_cluster_empty_registry(
        self, registry: CheckRegistry, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test getting checks for cluster when registry is empty."""
        checks = registry.get_checks_for_cluster(sample_cluster_config)
        assert checks == []


class TestRegistryClear:
    """Tests for clearing registry."""

    def test_clear_removes_all_checks(
        self, registry: CheckRegistry, sample_check: MockCheck, non_critical_check: MockCheck
    ) -> None:
        """Test that clear removes all checks."""
        registry.register(sample_check)
        registry.register(non_critical_check)
        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get_all_checks() == []
        assert registry.get_check("sample_check") is None
        assert registry.get_check("non_critical_check") is None

    def test_clear_on_empty_registry(self, registry: CheckRegistry) -> None:
        """Test clearing an already empty registry."""
        registry.clear()
        assert len(registry) == 0

    def test_clear_updates_internal_structures(
        self, registry: CheckRegistry, sample_check: MockCheck
    ) -> None:
        """Test that clear updates both internal structures."""
        registry.register(sample_check)

        registry.clear()

        assert registry._checks == []
        assert registry._checks_by_name == {}


class TestRegistryLenOperator:
    """Tests for len() operator on registry."""

    def test_len_empty_registry(self, registry: CheckRegistry) -> None:
        """Test len() on empty registry."""
        assert len(registry) == 0

    def test_len_with_checks(
        self, registry: CheckRegistry, sample_check: MockCheck, non_critical_check: MockCheck
    ) -> None:
        """Test len() with multiple checks registered."""
        assert len(registry) == 0

        registry.register(sample_check)
        assert len(registry) == 1

        registry.register(non_critical_check)
        assert len(registry) == 2

    def test_len_after_unregister(self, registry: CheckRegistry, sample_check: MockCheck) -> None:
        """Test len() after unregistering a check."""
        registry.register(sample_check)
        assert len(registry) == 1

        registry.unregister("sample_check")
        assert len(registry) == 0
