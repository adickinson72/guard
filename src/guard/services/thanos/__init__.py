"""Thanos service module - all Thanos-specific logic consolidated here.

This module provides:
- ThanosService: Main service implementation
- Health checks for Query, Store, and Compactor components
- Validators for query latency and store availability
- Helm updater for Flux configurations
- Post-upgrade operations for Thanos-specific validations
"""

from guard.services.thanos.thanos_service import ThanosService

__all__ = ["ThanosService"]
