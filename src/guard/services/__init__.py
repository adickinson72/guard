"""Service-specific modules.

This package contains service-specific implementations for the multi-service
upgrade framework. Each service (Istio, Thanos, Prometheus) has its own
module with checks, validators, and operations.

Key components:
- BaseService: Abstract base class all services implement
- ServiceRegistry: Central registry for service lookup
- ServiceType: Enum of supported service types
"""

from guard.services.base import BaseService
from guard.services.service_registry import ServiceRegistry, register_all_services

__all__ = [
    "BaseService",
    "ServiceRegistry",
    "register_all_services",
]
