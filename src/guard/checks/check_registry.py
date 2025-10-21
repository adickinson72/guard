"""Registry for managing health checks."""


from guard.core.models import ClusterConfig
from guard.interfaces.check import Check
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class CheckRegistry:
    """Registry for health check management.

    This registry stores and manages health checks, allowing
    checks to be registered and retrieved for execution.
    """

    def __init__(self) -> None:
        """Initialize check registry."""
        self._checks: list[Check] = []
        self._checks_by_name: dict[str, Check] = {}
        logger.debug("check_registry_initialized")

    def register(self, check: Check) -> None:
        """Register a health check.

        Args:
            check: Health check to register
        """
        if check.name in self._checks_by_name:
            logger.warning("check_already_registered", check_name=check.name)
            return

        self._checks.append(check)
        self._checks_by_name[check.name] = check

        logger.debug("check_registered", check_name=check.name)

    def unregister(self, check_name: str) -> bool:
        """Unregister a health check.

        Args:
            check_name: Name of check to unregister

        Returns:
            True if check was found and removed
        """
        if check_name not in self._checks_by_name:
            logger.warning("check_not_found_for_unregister", check_name=check_name)
            return False

        check = self._checks_by_name[check_name]
        self._checks.remove(check)
        del self._checks_by_name[check_name]

        logger.debug("check_unregistered", check_name=check_name)
        return True

    def get_check(self, check_name: str) -> Check | None:
        """Get a check by name.

        Args:
            check_name: Name of the check

        Returns:
            Check if found, None otherwise
        """
        return self._checks_by_name.get(check_name)

    def get_all_checks(self) -> list[Check]:
        """Get all registered checks.

        Returns:
            List of all registered checks
        """
        return self._checks.copy()

    def get_checks_for_cluster(self, _cluster: ClusterConfig) -> list[Check]:
        """Get checks applicable for a specific cluster.

        Currently returns all checks. Future enhancement could
        filter checks based on cluster metadata/tags.

        Args:
            _cluster: Cluster configuration (reserved for future use)

        Returns:
            List of applicable checks
        """
        # Future: could filter based on cluster.metadata or tags
        return self.get_all_checks()

    def get_critical_checks(self) -> list[Check]:
        """Get only critical checks.

        Returns:
            List of critical checks
        """
        return [check for check in self._checks if check.is_critical]

    def clear(self) -> None:
        """Clear all registered checks."""
        self._checks.clear()
        self._checks_by_name.clear()
        logger.debug("check_registry_cleared")

    def __len__(self) -> int:
        """Get number of registered checks."""
        return len(self._checks)
