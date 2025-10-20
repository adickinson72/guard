"""Registry for managing validators."""

from guard.core.models import ClusterConfig
from guard.interfaces.validator import Validator
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class ValidatorRegistry:
    """Registry for validator management.

    This registry stores and manages validators, allowing
    validators to be registered and retrieved for execution.
    """

    def __init__(self):
        """Initialize validator registry."""
        self._validators: list[Validator] = []
        self._validators_by_name: dict[str, Validator] = {}
        logger.debug("validator_registry_initialized")

    def register(self, validator: Validator) -> None:
        """Register a validator.

        Args:
            validator: Validator to register
        """
        if validator.name in self._validators_by_name:
            logger.warning("validator_already_registered", validator_name=validator.name)
            return

        self._validators.append(validator)
        self._validators_by_name[validator.name] = validator

        logger.debug("validator_registered", validator_name=validator.name)

    def unregister(self, validator_name: str) -> bool:
        """Unregister a validator.

        Args:
            validator_name: Name of validator to unregister

        Returns:
            True if validator was found and removed
        """
        if validator_name not in self._validators_by_name:
            logger.warning("validator_not_found_for_unregister", validator_name=validator_name)
            return False

        validator = self._validators_by_name[validator_name]
        self._validators.remove(validator)
        del self._validators_by_name[validator_name]

        logger.debug("validator_unregistered", validator_name=validator_name)
        return True

    def get_validator(self, validator_name: str) -> Validator | None:
        """Get a validator by name.

        Args:
            validator_name: Name of the validator

        Returns:
            Validator if found, None otherwise
        """
        return self._validators_by_name.get(validator_name)

    def get_all_validators(self) -> list[Validator]:
        """Get all registered validators.

        Returns:
            List of all registered validators
        """
        return self._validators.copy()

    def get_validators(self, cluster: ClusterConfig) -> list[Validator]:
        """Get validators applicable for a specific cluster.

        Currently returns all validators. Future enhancement could
        filter validators based on cluster metadata/tags.

        Args:
            cluster: Cluster configuration

        Returns:
            List of applicable validators
        """
        # Future: could filter based on cluster.metadata or tags
        return self.get_all_validators()

    def get_critical_validators(self) -> list[Validator]:
        """Get only critical validators.

        Returns:
            List of critical validators
        """
        return [v for v in self._validators if v.is_critical]

    def clear(self) -> None:
        """Clear all registered validators."""
        self._validators.clear()
        self._validators_by_name.clear()
        logger.debug("validator_registry_cleared")

    def __len__(self) -> int:
        """Get number of registered validators."""
        return len(self._validators)
