"""Thanos validators.

Provides validators for Thanos post-upgrade validation:
- ThanosQueryLatencyValidator: Validates Query API latency after upgrade
- ThanosStoreAvailabilityValidator: Validates Store availability after upgrade
"""

from guard.services.thanos.validators.query_latency import ThanosQueryLatencyValidator
from guard.services.thanos.validators.store_availability import ThanosStoreAvailabilityValidator

__all__ = [
    "ThanosQueryLatencyValidator",
    "ThanosStoreAvailabilityValidator",
]
