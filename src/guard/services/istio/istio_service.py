"""Istio service facade - single entry point for all Istio operations."""

from guard.checks.check_registry import CheckRegistry
from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
from guard.interfaces.config_updater import ConfigUpdater
from guard.services.istio.checks.istioctl_analyze import IstioCtlAnalyzeCheck
from guard.services.istio.checks.sidecar_version import IstioSidecarVersionCheck
from guard.services.istio.validators.error_rate import IstioErrorRateValidator
from guard.services.istio.validators.latency import IstioLatencyValidator
from guard.utils.logging import get_logger
from guard.validation.validator_registry import ValidatorRegistry

logger = get_logger(__name__)


class IstioService:
    """Facade for all Istio-specific operations.

    This facade provides a single interface for:
    - Registering Istio-specific health checks
    - Registering Istio-specific validators
    - Getting Istio config updater

    Future: When implementing ServiceProvider pattern, this becomes
    the basis for IstioProvider.
    """

    def __init__(self) -> None:
        """Initialize Istio service."""
        logger.debug("istio_service_initialized")

    def register_checks(self, registry: CheckRegistry) -> None:
        """Register all Istio health checks.

        Args:
            registry: Check registry to register with
        """
        logger.info("registering_istio_checks")

        # Register Istio-specific checks
        registry.register(IstioCtlAnalyzeCheck())
        registry.register(IstioSidecarVersionCheck())

        logger.info("istio_checks_registered", count=2)

    def register_validators(self, registry: ValidatorRegistry) -> None:
        """Register all Istio validators.

        Args:
            registry: Validator registry to register with
        """
        logger.info("registering_istio_validators")

        # Register Istio-specific validators
        registry.register(IstioLatencyValidator())
        registry.register(IstioErrorRateValidator())

        logger.info("istio_validators_registered", count=2)

    def get_config_updater(self) -> ConfigUpdater:
        """Get Istio config updater.

        Returns:
            ConfigUpdater for Istio HelmRelease files
        """
        return IstioHelmUpdater()

    @property
    def service_name(self) -> str:
        """Get service name."""
        return "istio"

    @property
    def description(self) -> str:
        """Get service description."""
        return "Istio service mesh upgrade management"
