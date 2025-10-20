"""Config updater interface for GitOps configuration updates."""

from abc import ABC, abstractmethod
from pathlib import Path


class ConfigUpdater(ABC):
    """Abstract interface for GitOps configuration file updates.

    This interface defines how to update service version in GitOps configs.
    Different services may have different config formats (Helm, Kustomize, etc.)
    and different ways of specifying versions.

    Design Philosophy:
    - Knows HOW to update a specific config format
    - Doesn't know WHERE files are or WHEN to update them
    - Service-specific implementations (IstioHelmUpdater, PromtailHelmUpdater)
    - Can validate config after update
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the updater name for logging.

        Returns:
            Human-readable updater name
        """

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Get list of supported config formats.

        Returns:
            List of format names (e.g., ["flux-helmrelease", "kustomize"])
        """

    @abstractmethod
    async def update_version(
        self, file_path: Path, target_version: str, backup: bool = True
    ) -> bool:
        """Update version in a configuration file.

        Args:
            file_path: Path to config file
            target_version: Version to update to
            backup: Whether to create backup before update

        Returns:
            True if successful

        Raises:
            ConfigUpdaterError: If update fails
        """

    @abstractmethod
    async def get_current_version(self, file_path: Path) -> str:
        """Get current version from a configuration file.

        Args:
            file_path: Path to config file

        Returns:
            Current version string

        Raises:
            ConfigUpdaterError: If version cannot be read
        """

    @abstractmethod
    async def validate_config(self, file_path: Path) -> tuple[bool, list[str]]:
        """Validate configuration file syntax.

        Args:
            file_path: Path to config file

        Returns:
            Tuple of (is_valid, list of validation errors)

        Raises:
            ConfigUpdaterError: If validation cannot be performed
        """

    @abstractmethod
    async def supports_file(self, file_path: Path) -> bool:
        """Check if this updater supports the given file.

        Args:
            file_path: Path to config file

        Returns:
            True if this updater can handle the file

        Raises:
            ConfigUpdaterError: If check fails
        """
