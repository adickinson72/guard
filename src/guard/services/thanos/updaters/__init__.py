"""Thanos config updaters.

Provides config updaters for Thanos GitOps configurations:
- ThanosHelmUpdater: Updates Thanos version in Flux HelmRelease files
"""

from guard.services.thanos.updaters.helm_updater import ThanosHelmUpdater

__all__ = [
    "ThanosHelmUpdater",
]
