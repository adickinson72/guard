"""Thanos health checks.

Provides health checks for Thanos components:
- ThanosQueryHealthCheck: Validates Query pods are healthy
- ThanosStoreHealthCheck: Validates Store gateway pods are healthy
- ThanosCompactorHealthCheck: Validates Compactor pods are healthy (optional)
"""

from guard.services.thanos.checks.compactor_health import ThanosCompactorHealthCheck
from guard.services.thanos.checks.query_health import ThanosQueryHealthCheck
from guard.services.thanos.checks.store_health import ThanosStoreHealthCheck

__all__ = [
    "ThanosQueryHealthCheck",
    "ThanosStoreHealthCheck",
    "ThanosCompactorHealthCheck",
]
