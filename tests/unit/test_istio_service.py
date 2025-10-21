"""Unit tests for IstioService facade.

This module tests the IstioService facade which provides a single interface
for all Istio-specific operations including check registration, validator
registration, and config updater retrieval.
"""

from unittest.mock import patch

import pytest

from guard.checks.check_registry import CheckRegistry
from guard.services.istio.istio_service import IstioService
from guard.validation.validator_registry import ValidatorRegistry


@pytest.fixture
def istio_service() -> IstioService:
    """Create IstioService instance for testing.

    Returns:
        IstioService instance
    """
    return IstioService()


@pytest.fixture
def mock_check_registry() -> CheckRegistry:
    """Create mock CheckRegistry for testing.

    Returns:
        Mock CheckRegistry
    """
    return CheckRegistry()


@pytest.fixture
def mock_validator_registry() -> ValidatorRegistry:
    """Create mock ValidatorRegistry for testing.

    Returns:
        Mock ValidatorRegistry
    """
    return ValidatorRegistry()


class TestIstioServiceInitialization:
    """Test IstioService initialization."""

    def test_istio_service_initialization(self, istio_service: IstioService):
        """Test that IstioService initializes successfully.

        Args:
            istio_service: IstioService instance
        """
        assert istio_service is not None
        assert isinstance(istio_service, IstioService)

    def test_service_name_property(self, istio_service: IstioService):
        """Test that service_name property returns correct value.

        Args:
            istio_service: IstioService instance
        """
        assert istio_service.service_name == "istio"

    def test_description_property(self, istio_service: IstioService):
        """Test that description property returns correct value.

        Args:
            istio_service: IstioService instance
        """
        assert istio_service.description == "Istio service mesh upgrade management"
        assert len(istio_service.description) > 0


class TestIstioServiceCheckRegistration:
    """Test IstioService check registration."""

    def test_register_checks_adds_istio_checks(
        self, istio_service: IstioService, mock_check_registry: CheckRegistry
    ):
        """Test that register_checks adds all Istio checks to registry.

        Args:
            istio_service: IstioService instance
            mock_check_registry: Mock CheckRegistry
        """
        # Initially registry should be empty
        assert len(mock_check_registry) == 0

        # Register checks
        istio_service.register_checks(mock_check_registry)

        # Verify checks were registered
        assert len(mock_check_registry) == 2

        # Verify specific checks exist
        assert mock_check_registry.get_check("istioctl_analyze") is not None
        assert mock_check_registry.get_check("istio_sidecar_version") is not None

    def test_register_checks_with_istioctl_analyze(
        self, istio_service: IstioService, mock_check_registry: CheckRegistry
    ):
        """Test that IstioCtlAnalyzeCheck is properly registered.

        Args:
            istio_service: IstioService instance
            mock_check_registry: Mock CheckRegistry
        """
        istio_service.register_checks(mock_check_registry)

        check = mock_check_registry.get_check("istioctl_analyze")
        assert check is not None
        assert check.name == "istioctl_analyze"
        assert "istioctl" in check.description.lower()

    def test_register_checks_with_sidecar_version(
        self, istio_service: IstioService, mock_check_registry: CheckRegistry
    ):
        """Test that IstioSidecarVersionCheck is properly registered.

        Args:
            istio_service: IstioService instance
            mock_check_registry: Mock CheckRegistry
        """
        istio_service.register_checks(mock_check_registry)

        check = mock_check_registry.get_check("istio_sidecar_version")
        assert check is not None
        assert check.name == "istio_sidecar_version"
        assert "sidecar" in check.description.lower()

    def test_register_checks_logs_registration(
        self, istio_service: IstioService, mock_check_registry: CheckRegistry
    ):
        """Test that check registration is properly logged.

        Args:
            istio_service: IstioService instance
            mock_check_registry: Mock CheckRegistry
        """
        with patch("guard.services.istio.istio_service.logger") as mock_logger:
            istio_service.register_checks(mock_check_registry)

            # Verify logging calls
            mock_logger.info.assert_any_call("registering_istio_checks")
            mock_logger.info.assert_any_call("istio_checks_registered", count=2)


class TestIstioServiceValidatorRegistration:
    """Test IstioService validator registration."""

    def test_register_validators_adds_istio_validators(
        self, istio_service: IstioService, mock_validator_registry: ValidatorRegistry
    ):
        """Test that register_validators adds all Istio validators to registry.

        Args:
            istio_service: IstioService instance
            mock_validator_registry: Mock ValidatorRegistry
        """
        # Initially registry should be empty
        assert len(mock_validator_registry) == 0

        # Register validators
        istio_service.register_validators(mock_validator_registry)

        # Verify validators were registered
        assert len(mock_validator_registry) == 2

        # Verify specific validators exist
        assert mock_validator_registry.get_validator("istio_latency") is not None
        assert mock_validator_registry.get_validator("istio_error_rate") is not None

    def test_register_validators_with_latency(
        self, istio_service: IstioService, mock_validator_registry: ValidatorRegistry
    ):
        """Test that IstioLatencyValidator is properly registered.

        Args:
            istio_service: IstioService instance
            mock_validator_registry: Mock ValidatorRegistry
        """
        istio_service.register_validators(mock_validator_registry)

        validator = mock_validator_registry.get_validator("istio_latency")
        assert validator is not None
        assert validator.name == "istio_latency"
        assert "latency" in validator.description.lower()

    def test_register_validators_with_error_rate(
        self, istio_service: IstioService, mock_validator_registry: ValidatorRegistry
    ):
        """Test that IstioErrorRateValidator is properly registered.

        Args:
            istio_service: IstioService instance
            mock_validator_registry: Mock ValidatorRegistry
        """
        istio_service.register_validators(mock_validator_registry)

        validator = mock_validator_registry.get_validator("istio_error_rate")
        assert validator is not None
        assert validator.name == "istio_error_rate"
        assert "error" in validator.description.lower()

    def test_register_validators_logs_registration(
        self, istio_service: IstioService, mock_validator_registry: ValidatorRegistry
    ):
        """Test that validator registration is properly logged.

        Args:
            istio_service: IstioService instance
            mock_validator_registry: Mock ValidatorRegistry
        """
        with patch("guard.services.istio.istio_service.logger") as mock_logger:
            istio_service.register_validators(mock_validator_registry)

            # Verify logging calls
            mock_logger.info.assert_any_call("registering_istio_validators")
            mock_logger.info.assert_any_call("istio_validators_registered", count=2)


class TestIstioServiceConfigUpdater:
    """Test IstioService config updater."""

    def test_get_config_updater_returns_istio_helm_updater(self, istio_service: IstioService):
        """Test that get_config_updater returns IstioHelmUpdater.

        Args:
            istio_service: IstioService instance
        """
        updater = istio_service.get_config_updater()

        assert updater is not None
        # Check that it's an IstioHelmUpdater by checking type name
        assert type(updater).__name__ == "IstioHelmUpdater"

    def test_get_config_updater_returns_config_updater_interface(self, istio_service: IstioService):
        """Test that get_config_updater returns ConfigUpdater interface.

        Args:
            istio_service: IstioService instance
        """
        from guard.interfaces.config_updater import ConfigUpdater

        updater = istio_service.get_config_updater()

        # Verify it implements the ConfigUpdater interface
        assert isinstance(updater, ConfigUpdater)
        assert hasattr(updater, "update_version")
        assert hasattr(updater, "get_current_version")
        assert hasattr(updater, "validate_config")
        assert hasattr(updater, "supports_file")
        assert hasattr(updater, "name")
        assert hasattr(updater, "supported_formats")

    def test_get_config_updater_returns_new_instance_each_time(self, istio_service: IstioService):
        """Test that get_config_updater returns a new instance each time.

        Args:
            istio_service: IstioService instance
        """
        updater1 = istio_service.get_config_updater()
        updater2 = istio_service.get_config_updater()

        # Should be different instances
        assert updater1 is not updater2


class TestIstioServiceIntegration:
    """Test IstioService integration scenarios."""

    def test_full_service_registration_workflow(self, istio_service: IstioService):
        """Test complete workflow of registering checks and validators.

        Args:
            istio_service: IstioService instance
        """
        check_registry = CheckRegistry()
        validator_registry = ValidatorRegistry()

        # Register checks
        istio_service.register_checks(check_registry)
        assert len(check_registry) == 2

        # Register validators
        istio_service.register_validators(validator_registry)
        assert len(validator_registry) == 2

        # Get config updater
        updater = istio_service.get_config_updater()
        assert updater is not None

    def test_multiple_istio_service_instances_independent(self):
        """Test that multiple IstioService instances are independent."""
        service1 = IstioService()
        service2 = IstioService()

        # Different instances
        assert service1 is not service2

        # Same service name and description
        assert service1.service_name == service2.service_name
        assert service1.description == service2.description

    def test_register_to_multiple_registries(self, istio_service: IstioService):
        """Test that checks can be registered to multiple registries.

        Args:
            istio_service: IstioService instance
        """
        registry1 = CheckRegistry()
        registry2 = CheckRegistry()

        # Register to both registries
        istio_service.register_checks(registry1)
        istio_service.register_checks(registry2)

        # Both should have checks
        assert len(registry1) == 2
        assert len(registry2) == 2

        # But they should be independent
        registry1.clear()
        assert len(registry1) == 0
        assert len(registry2) == 2
