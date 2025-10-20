"""Flux configuration parser and updater."""

import yaml

from guard.utils.logging import get_logger

logger = get_logger(__name__)


class FluxConfigManager:
    """Manager for Flux configuration files."""

    @staticmethod
    def parse_helmrelease(content: str) -> dict:
        """Parse HelmRelease YAML.

        Args:
            content: YAML content

        Returns:
            Parsed dict
        """
        return yaml.safe_load(content)

    @staticmethod
    def update_version(config: dict, new_version: str) -> dict:
        """Update Istio version in HelmRelease config.

        Args:
            config: HelmRelease config dict
            new_version: New Istio version (e.g., "1.20.0" or "v1.20.0")

        Returns:
            Updated config dict

        Raises:
            ValueError: If config structure is invalid
        """
        logger.info("updating_version", new_version=new_version)

        # Validate config structure
        if not config:
            raise ValueError("Empty configuration")

        if "spec" not in config:
            raise ValueError("Missing 'spec' in HelmRelease")

        if "chart" not in config["spec"]:
            raise ValueError("Missing 'spec.chart' in HelmRelease")

        if "spec" not in config["spec"]["chart"]:
            raise ValueError("Missing 'spec.chart.spec' in HelmRelease")

        # Clean version (remove 'v' prefix if present)
        clean_version = new_version.lstrip("v")

        # Get old version for logging
        old_version = config["spec"]["chart"]["spec"].get("version", "unknown")

        # Update version
        config["spec"]["chart"]["spec"]["version"] = clean_version

        logger.info(
            "version_updated",
            old_version=old_version,
            new_version=clean_version,
        )

        return config

    @staticmethod
    def to_yaml(config: dict) -> str:
        """Convert config to YAML.

        Args:
            config: Config dict

        Returns:
            YAML string
        """
        return yaml.dump(config, default_flow_style=False)
