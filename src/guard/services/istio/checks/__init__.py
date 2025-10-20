"""Istio-specific health checks."""

from guard.services.istio.checks.istioctl_analyze import IstioCtlAnalyzeCheck
from guard.services.istio.checks.sidecar_version import IstioSidecarVersionCheck

__all__ = [
    "IstioCtlAnalyzeCheck",
    "IstioSidecarVersionCheck",
]
