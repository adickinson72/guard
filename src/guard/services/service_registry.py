"""Central registry for service implementations."""

from typing import TYPE_CHECKING, ClassVar

from guard.core.models import ServiceType
from guard.utils.logging import get_logger

if TYPE_CHECKING:
    from guard.services.base import BaseService

logger = get_logger(__name__)


class ServiceRegistry:
    """Central registry for service implementations.

    Provides factory method to get service implementation by type.
    Uses singleton pattern for service instances.

    Usage:
        # Get a service by type
        service = ServiceRegistry.get(ServiceType.ISTIO)

        # Check if a service is registered
        if ServiceRegistry.is_registered(ServiceType.THANOS):
            thanos = ServiceRegistry.get(ServiceType.THANOS)

        # Get all registered services
        for service in ServiceRegistry.get_all():
            print(service.service_name)
    """

    _services: ClassVar[dict[ServiceType, type["BaseService"]]] = {}
    _instances: ClassVar[dict[ServiceType, "BaseService"]] = {}

    @classmethod
    def register(cls, service_type: ServiceType, service_class: type["BaseService"]) -> None:
        """Register a service implementation.

        Args:
            service_type: Service type enum value
            service_class: Service class (not instance) to register

        Raises:
            ValueError: If service type is already registered
        """
        if service_type in cls._services:
            logger.warning(
                "service_already_registered",
                service_type=service_type.value,
                existing_class=cls._services[service_type].__name__,
                new_class=service_class.__name__,
            )
            # Allow re-registration for testing
        cls._services[service_type] = service_class
        # Clear cached instance if re-registering
        cls._instances.pop(service_type, None)
        logger.debug("service_registered", service_type=service_type.value)

    @classmethod
    def get(cls, service_type: ServiceType) -> "BaseService":
        """Get service instance (singleton per type).

        Args:
            service_type: Service type to get

        Returns:
            Service instance

        Raises:
            ValueError: If service type is not registered
        """
        if service_type not in cls._services:
            available = [s.value for s in cls._services]
            raise ValueError(
                f"Unknown service type: {service_type.value}. " f"Available services: {available}"
            )

        if service_type not in cls._instances:
            cls._instances[service_type] = cls._services[service_type]()
            logger.debug(
                "service_instance_created",
                service_type=service_type.value,
            )

        return cls._instances[service_type]

    @classmethod
    def get_all(cls) -> list["BaseService"]:
        """Get all registered service instances.

        Returns:
            List of all service instances
        """
        return [cls.get(st) for st in cls._services]

    @classmethod
    def is_registered(cls, service_type: ServiceType) -> bool:
        """Check if a service type is registered.

        Args:
            service_type: Service type to check

        Returns:
            True if registered, False otherwise
        """
        return service_type in cls._services

    @classmethod
    def get_registered_types(cls) -> list[ServiceType]:
        """Get all registered service types.

        Returns:
            List of registered ServiceType values
        """
        return list(cls._services.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing).

        Removes all service classes and instances from the registry.
        """
        cls._services.clear()
        cls._instances.clear()
        logger.debug("service_registry_cleared")


def register_all_services() -> None:
    """Register all available service implementations.

    Call this function during application startup to register
    all service implementations with the registry.
    """
    # Import services here to avoid circular imports
    from guard.services.istio.istio_service import IstioService

    ServiceRegistry.register(ServiceType.ISTIO, IstioService)

    # Thanos and Prometheus will be registered when implemented
    # from guard.services.thanos.thanos_service import ThanosService
    # from guard.services.prometheus.prometheus_service import PrometheusService
    # ServiceRegistry.register(ServiceType.THANOS, ThanosService)
    # ServiceRegistry.register(ServiceType.PROMETHEUS, PrometheusService)

    logger.info(
        "services_registered",
        count=len(ServiceRegistry.get_registered_types()),
        services=[s.value for s in ServiceRegistry.get_registered_types()],
    )
