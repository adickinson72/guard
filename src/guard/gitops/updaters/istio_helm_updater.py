"""Istio Helm updater for Flux HelmRelease configurations."""

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml

from guard.core.models import UpgradeSpec
from guard.interfaces.config_updater import ConfigUpdater
from guard.interfaces.exceptions import ConfigUpdaterError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioHelmUpdater(ConfigUpdater):
    """Config updater for Istio Flux HelmRelease files.

    This updater knows how to update Istio version in Flux HelmRelease
    YAML configuration files.
    """

    @property
    def name(self) -> str:
        """Get updater name."""
        return "istio_helm_updater"

    @property
    def supported_formats(self) -> list[str]:
        """Get supported config formats."""
        return ["flux-helmrelease", "helmrelease"]

    async def update_version(
        self,
        file_path: Path,
        target_version: str,
        backup: bool = True,
    ) -> bool:
        """Update Istio version in HelmRelease file.

        Args:
            file_path: Path to HelmRelease YAML file
            target_version: Istio version to set
            backup: Create backup before update

        Returns:
            True if successful

        Raises:
            ConfigUpdaterError: If update fails
        """
        try:
            logger.info(
                "updating_istio_version",
                file_path=str(file_path),
                target_version=target_version,
            )

            # Backup if requested
            if backup:
                # Add .bak to preserve original extension (e.g., config.yaml -> config.yaml.bak)
                backup_path = Path(str(file_path) + ".bak")
                shutil.copy(file_path, backup_path)
                logger.debug("backup_created", backup_path=str(backup_path))

            # Load YAML
            with open(file_path) as f:
                config = yaml.safe_load(f)

            if not config:
                raise ConfigUpdaterError(f"Empty or invalid YAML in {file_path}")

            # Update version
            # Typical Flux HelmRelease structure:
            # spec:
            #   chart:
            #     spec:
            #       version: "1.20.0"
            if "spec" not in config:
                raise ConfigUpdaterError("Missing 'spec' in HelmRelease")

            if "chart" not in config["spec"]:
                raise ConfigUpdaterError("Missing 'spec.chart' in HelmRelease")

            if "spec" not in config["spec"]["chart"]:
                raise ConfigUpdaterError("Missing 'spec.chart.spec' in HelmRelease")

            # Clean version (remove 'v' prefix if present)
            clean_version = target_version.lstrip("v")

            # Update version
            old_version = config["spec"]["chart"]["spec"].get("version", "unknown")
            config["spec"]["chart"]["spec"]["version"] = clean_version

            # Write back
            with open(file_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(
                "istio_version_updated",
                file_path=str(file_path),
                old_version=old_version,
                new_version=clean_version,
            )

            return True

        except Exception as e:
            logger.error(
                "update_version_failed",
                file_path=str(file_path),
                error=str(e),
            )
            raise ConfigUpdaterError(f"Failed to update version in {file_path}: {e}") from e

    async def get_current_version(self, file_path: Path) -> str:
        """Get current Istio version from HelmRelease file.

        Args:
            file_path: Path to HelmRelease YAML file

        Returns:
            Current version string

        Raises:
            ConfigUpdaterError: If version cannot be read
        """
        try:
            logger.debug("getting_current_version", file_path=str(file_path))

            with open(file_path) as f:
                config = yaml.safe_load(f)

            if not config:
                raise ConfigUpdaterError(f"Empty or invalid YAML in {file_path}")

            # Navigate to version
            version = config.get("spec", {}).get("chart", {}).get("spec", {}).get("version")

            if not version:
                raise ConfigUpdaterError(f"Version not found in {file_path}")

            logger.info("current_version_retrieved", version=version)
            return version

        except Exception as e:
            logger.error(
                "get_current_version_failed",
                file_path=str(file_path),
                error=str(e),
            )
            raise ConfigUpdaterError(f"Failed to get current version: {e}") from e

    async def validate_config(self, file_path: Path) -> tuple[bool, list[str]]:
        """Validate HelmRelease configuration.

        Args:
            file_path: Path to config file

        Returns:
            Tuple of (is_valid, list of validation errors)

        Raises:
            ConfigUpdaterError: If validation cannot be performed
        """
        try:
            logger.debug("validating_config", file_path=str(file_path))

            errors = []

            # Check file exists
            if not file_path.exists():
                errors.append(f"File does not exist: {file_path}")
                return False, errors

            # Try to load YAML
            try:
                with open(file_path) as f:
                    config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                errors.append(f"Invalid YAML: {e}")
                return False, errors

            if not config:
                errors.append("Empty configuration file")
                return False, errors

            # Validate structure
            if "apiVersion" not in config:
                errors.append("Missing 'apiVersion' field")

            if "kind" not in config:
                errors.append("Missing 'kind' field")
            elif config["kind"] != "HelmRelease":
                errors.append(f"Expected kind 'HelmRelease', got '{config['kind']}'")

            if "spec" not in config:
                errors.append("Missing 'spec' field")
            else:
                if "chart" not in config["spec"]:
                    errors.append("Missing 'spec.chart' field")
                else:
                    if "spec" not in config["spec"]["chart"]:
                        errors.append("Missing 'spec.chart.spec' field")
                    else:
                        if "version" not in config["spec"]["chart"]["spec"]:
                            errors.append("Missing 'spec.chart.spec.version' field")

            is_valid = len(errors) == 0
            logger.info("config_validated", is_valid=is_valid, error_count=len(errors))

            return is_valid, errors

        except Exception as e:
            logger.error("validate_config_failed", file_path=str(file_path), error=str(e))
            raise ConfigUpdaterError(f"Failed to validate config: {e}") from e

    async def supports_file(self, file_path: Path) -> bool:
        """Check if this updater supports the given file.

        Args:
            file_path: Path to config file

        Returns:
            True if this updater can handle the file

        Raises:
            ConfigUpdaterError: If check fails
        """
        try:
            # Check file extension
            if file_path.suffix not in [".yaml", ".yml"]:
                return False

            # Check if it's a HelmRelease
            with open(file_path) as f:
                config = yaml.safe_load(f)

            if not config:
                return False

            # Check if it's a HelmRelease for Istio
            is_helmrelease = config.get("kind") == "HelmRelease"

            # Could also check if it's Istio-specific by looking at chart name
            # chart_name = config.get("spec", {}).get("chart", {}).get("spec", {}).get("chart")
            # is_istio = "istio" in (chart_name or "").lower()

            return is_helmrelease

        except Exception as e:
            logger.error("supports_file_check_failed", file_path=str(file_path), error=str(e))
            return False

    @staticmethod
    def _set_nested_value(data: dict, path: str, value: Any, create_missing: bool = False) -> None:
        """Set a value in a nested dictionary using dotted path notation.

        Args:
            data: Dictionary to update
            path: Dotted path (e.g., 'spec.chart.spec.version')
            value: Value to set
            create_missing: If True, create intermediate dicts. If False (default),
                           raise ValueError if path doesn't exist. This prevents
                           silent corruption from typos.

        Raises:
            ValueError: If path is invalid or parent doesn't exist (when create_missing=False)
        """
        # Import here to avoid circular dependency
        from guard.core.models import FieldUpdate

        # Validate path format before proceeding
        if not FieldUpdate.validate_path(path):
            raise ValueError(
                f"Invalid path format: '{path}'. "
                f"Path must not contain consecutive dots, leading/trailing dots, or empty parts."
            )

        parts = path.split(".")
        current = data

        # Navigate to the parent of the target field
        for part in parts[:-1]:
            if part not in current:
                if create_missing:
                    # Create intermediate dictionaries if allowed
                    current[part] = {}
                    logger.debug(
                        "creating_intermediate_dict",
                        path=path,
                        created_key=part,
                    )
                else:
                    # Fail fast to prevent silent corruption
                    raise ValueError(
                        f"Path '{path}' does not exist: missing key '{part}'. "
                        f"Use create_missing=True to create intermediate dictionaries."
                    )
            if not isinstance(current[part], dict):
                raise ValueError(f"Cannot navigate path '{path}': '{part}' is not a dictionary")
            current = current[part]

        # Set the final value
        final_key = parts[-1]
        logger.debug(
            "setting_field",
            path=path,
            key=final_key,
            value=value,
        )
        current[final_key] = value

    async def apply_upgrade_spec(
        self,
        file_path: Path,
        upgrade_spec: UpgradeSpec,
        backup: bool = True,
    ) -> bool:
        """Apply upgrade specification to HelmRelease file.

        Args:
            file_path: Path to HelmRelease YAML file
            upgrade_spec: Upgrade specification with field updates
            backup: Create backup before update

        Returns:
            True if successful

        Raises:
            ConfigUpdaterError: If update fails
        """
        try:
            # Note: Path validation is now enforced via Pydantic @model_validator
            # during UpgradeSpec deserialization, so no need to validate here.
            logger.info(
                "applying_upgrade_spec",
                file_path=str(file_path),
                version=upgrade_spec.version,
                update_count=len(upgrade_spec.updates),
            )

            # Backup if requested
            if backup:
                try:
                    # Add .bak to preserve original extension (e.g., config.yaml -> config.yaml.bak)
                    backup_path = Path(str(file_path) + ".bak")
                    shutil.copy(file_path, backup_path)
                    logger.debug("backup_created", backup_path=str(backup_path))
                except (OSError, PermissionError) as e:
                    raise ConfigUpdaterError(
                        f"Failed to create backup file at {backup_path}: {e}"
                    ) from e

            # Load YAML
            with open(file_path) as f:
                config = yaml.safe_load(f)

            if not config:
                raise ConfigUpdaterError(f"Empty or invalid YAML in {file_path}")

            # Create deep copy to apply updates atomically
            # This prevents partial updates if any field update fails
            updated_config = copy.deepcopy(config)

            # Apply each field update to the copy
            for update in upgrade_spec.updates:
                try:
                    self._set_nested_value(updated_config, update.path, update.value)
                    logger.debug(
                        "field_updated",
                        path=update.path,
                        value=update.value,
                    )
                except Exception as e:
                    logger.error(
                        "field_update_failed",
                        path=update.path,
                        error=str(e),
                    )
                    raise ConfigUpdaterError(f"Failed to update field '{update.path}': {e}") from e

            # Write back (only if all updates succeeded)
            with open(file_path, "w") as f:
                yaml.dump(updated_config, f, default_flow_style=False, sort_keys=False)

            logger.info(
                "upgrade_spec_applied_successfully",
                file_path=str(file_path),
                version=upgrade_spec.version,
            )

            return True

        except ConfigUpdaterError:
            # Re-raise ConfigUpdaterError as-is (these are already properly formatted)
            raise
        except yaml.YAMLError as e:
            logger.error(
                "yaml_processing_failed",
                file_path=str(file_path),
                error=str(e),
            )
            raise ConfigUpdaterError(f"YAML processing error in {file_path}: {e}") from e
        except OSError as e:
            logger.error(
                "file_io_failed",
                file_path=str(file_path),
                error=str(e),
            )
            raise ConfigUpdaterError(f"File I/O error for {file_path}: {e}") from e
        except Exception as e:
            logger.error(
                "apply_upgrade_spec_failed",
                file_path=str(file_path),
                error=str(e),
            )
            raise ConfigUpdaterError(
                f"Unexpected error applying upgrade spec to {file_path}: {e}"
            ) from e
