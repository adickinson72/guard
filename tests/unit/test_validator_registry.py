"""Unit tests for ValidatorRegistry.

Tests the validator registry for managing and retrieving validators.
All validators are mocked to ensure tests are isolated and fast.
"""

from unittest.mock import MagicMock

import pytest

from guard.core.models import ClusterConfig
from guard.interfaces.validator import Validator
from guard.validation.validator_registry import ValidatorRegistry


@pytest.fixture
def registry() -> ValidatorRegistry:
    """Create a fresh validator registry for each test."""
    return ValidatorRegistry()


@pytest.fixture
def mock_validator() -> MagicMock:
    """Create a mock validator."""
    validator = MagicMock(spec=Validator)
    validator.name = "test_validator"
    validator.description = "Test validator description"
    validator.is_critical = True
    validator.timeout_seconds = 60
    return validator


@pytest.fixture
def mock_non_critical_validator() -> MagicMock:
    """Create a mock non-critical validator."""
    validator = MagicMock(spec=Validator)
    validator.name = "non_critical_validator"
    validator.description = "Non-critical test validator"
    validator.is_critical = False
    validator.timeout_seconds = 30
    return validator


class TestValidatorRegistryInit:
    """Tests for ValidatorRegistry initialization."""

    def test_init_creates_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test that initialization creates an empty registry."""
        assert len(registry) == 0
        assert registry.get_all_validators() == []


class TestValidatorRegistryRegister:
    """Tests for validator registration."""

    def test_register_validator_success(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test successful validator registration."""
        registry.register(mock_validator)

        assert len(registry) == 1
        assert registry.get_validator("test_validator") == mock_validator

    def test_register_multiple_validators(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test registering multiple validators."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)

        assert len(registry) == 2
        assert registry.get_validator("test_validator") == mock_validator
        assert registry.get_validator("non_critical_validator") == mock_non_critical_validator

    def test_register_duplicate_validator_logs_warning(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test that registering a duplicate validator logs a warning and doesn't add it."""
        registry.register(mock_validator)
        registry.register(mock_validator)  # Try to register again

        assert len(registry) == 1
        validators = registry.get_all_validators()
        assert len(validators) == 1

    def test_register_validator_with_same_name_ignored(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test that registering validators with the same name is ignored."""
        registry.register(mock_validator)

        # Create another validator with same name
        duplicate = MagicMock(spec=Validator)
        duplicate.name = "test_validator"
        duplicate.description = "Different description"

        registry.register(duplicate)

        assert len(registry) == 1
        # Original validator should still be there
        assert registry.get_validator("test_validator") == mock_validator


class TestValidatorRegistryUnregister:
    """Tests for validator unregistration."""

    def test_unregister_existing_validator_success(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test successful unregistration of existing validator."""
        registry.register(mock_validator)
        assert len(registry) == 1

        result = registry.unregister("test_validator")

        assert result is True
        assert len(registry) == 0
        assert registry.get_validator("test_validator") is None

    def test_unregister_non_existent_validator_returns_false(
        self, registry: ValidatorRegistry
    ) -> None:
        """Test unregistering a non-existent validator returns False."""
        result = registry.unregister("non_existent_validator")

        assert result is False

    def test_unregister_from_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test unregistering from an empty registry."""
        result = registry.unregister("test_validator")

        assert result is False
        assert len(registry) == 0

    def test_unregister_removes_correct_validator(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test that unregister removes the correct validator."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)
        assert len(registry) == 2

        registry.unregister("test_validator")

        assert len(registry) == 1
        assert registry.get_validator("test_validator") is None
        assert registry.get_validator("non_critical_validator") == mock_non_critical_validator


class TestValidatorRegistryGetValidator:
    """Tests for getting individual validators."""

    def test_get_existing_validator(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test getting an existing validator by name."""
        registry.register(mock_validator)

        validator = registry.get_validator("test_validator")

        assert validator == mock_validator

    def test_get_non_existent_validator_returns_none(
        self, registry: ValidatorRegistry
    ) -> None:
        """Test getting a non-existent validator returns None."""
        validator = registry.get_validator("non_existent_validator")

        assert validator is None

    def test_get_validator_from_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test getting validator from empty registry returns None."""
        validator = registry.get_validator("test_validator")

        assert validator is None


class TestValidatorRegistryGetAllValidators:
    """Tests for getting all validators."""

    def test_get_all_validators_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test getting all validators from empty registry."""
        validators = registry.get_all_validators()

        assert validators == []
        assert isinstance(validators, list)

    def test_get_all_validators_returns_copy(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test that get_all_validators returns a copy, not the internal list."""
        registry.register(mock_validator)

        validators1 = registry.get_all_validators()
        validators2 = registry.get_all_validators()

        # Should be equal but not the same object
        assert validators1 == validators2
        assert validators1 is not validators2

    def test_get_all_validators_multiple(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test getting all validators when multiple are registered."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)

        validators = registry.get_all_validators()

        assert len(validators) == 2
        assert mock_validator in validators
        assert mock_non_critical_validator in validators


class TestValidatorRegistryGetValidators:
    """Tests for getting validators for a specific cluster."""

    def test_get_validators_returns_all_validators(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test that get_validators currently returns all validators for any cluster."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)

        validators = registry.get_validators(sample_cluster_config)

        assert len(validators) == 2
        assert mock_validator in validators
        assert mock_non_critical_validator in validators

    def test_get_validators_empty_registry(
        self, registry: ValidatorRegistry, sample_cluster_config: ClusterConfig
    ) -> None:
        """Test getting validators from empty registry."""
        validators = registry.get_validators(sample_cluster_config)

        assert validators == []

    def test_get_validators_returns_copy(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        sample_cluster_config: ClusterConfig,
    ) -> None:
        """Test that get_validators returns a copy."""
        registry.register(mock_validator)

        validators1 = registry.get_validators(sample_cluster_config)
        validators2 = registry.get_validators(sample_cluster_config)

        assert validators1 == validators2
        assert validators1 is not validators2


class TestValidatorRegistryGetCriticalValidators:
    """Tests for getting only critical validators."""

    def test_get_critical_validators_only(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test getting only critical validators."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)

        critical_validators = registry.get_critical_validators()

        assert len(critical_validators) == 1
        assert mock_validator in critical_validators
        assert mock_non_critical_validator not in critical_validators

    def test_get_critical_validators_empty_registry(
        self, registry: ValidatorRegistry
    ) -> None:
        """Test getting critical validators from empty registry."""
        critical_validators = registry.get_critical_validators()

        assert critical_validators == []

    def test_get_critical_validators_all_non_critical(
        self, registry: ValidatorRegistry, mock_non_critical_validator: MagicMock
    ) -> None:
        """Test getting critical validators when all are non-critical."""
        registry.register(mock_non_critical_validator)

        critical_validators = registry.get_critical_validators()

        assert critical_validators == []

    def test_get_critical_validators_multiple_critical(
        self, registry: ValidatorRegistry
    ) -> None:
        """Test getting multiple critical validators."""
        # Create multiple critical validators
        validator1 = MagicMock(spec=Validator)
        validator1.name = "critical_1"
        validator1.is_critical = True

        validator2 = MagicMock(spec=Validator)
        validator2.name = "critical_2"
        validator2.is_critical = True

        validator3 = MagicMock(spec=Validator)
        validator3.name = "non_critical"
        validator3.is_critical = False

        registry.register(validator1)
        registry.register(validator2)
        registry.register(validator3)

        critical_validators = registry.get_critical_validators()

        assert len(critical_validators) == 2
        assert validator1 in critical_validators
        assert validator2 in critical_validators
        assert validator3 not in critical_validators


class TestValidatorRegistryClear:
    """Tests for clearing the registry."""

    def test_clear_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test clearing an empty registry."""
        registry.clear()

        assert len(registry) == 0
        assert registry.get_all_validators() == []

    def test_clear_removes_all_validators(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test that clear removes all validators."""
        registry.register(mock_validator)
        registry.register(mock_non_critical_validator)
        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get_all_validators() == []
        assert registry.get_validator("test_validator") is None
        assert registry.get_validator("non_critical_validator") is None

    def test_clear_allows_re_registration(
        self, registry: ValidatorRegistry, mock_validator: MagicMock
    ) -> None:
        """Test that validators can be re-registered after clear."""
        registry.register(mock_validator)
        registry.clear()

        # Should be able to register again
        registry.register(mock_validator)

        assert len(registry) == 1
        assert registry.get_validator("test_validator") == mock_validator


class TestValidatorRegistryLen:
    """Tests for registry length."""

    def test_len_empty_registry(self, registry: ValidatorRegistry) -> None:
        """Test length of empty registry."""
        assert len(registry) == 0

    def test_len_with_validators(
        self,
        registry: ValidatorRegistry,
        mock_validator: MagicMock,
        mock_non_critical_validator: MagicMock,
    ) -> None:
        """Test length reflects number of registered validators."""
        registry.register(mock_validator)
        assert len(registry) == 1

        registry.register(mock_non_critical_validator)
        assert len(registry) == 2

        registry.unregister("test_validator")
        assert len(registry) == 1

        registry.clear()
        assert len(registry) == 0
