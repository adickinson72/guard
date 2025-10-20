"""Istio-specific validators."""

from guard.services.istio.validators.error_rate import IstioErrorRateValidator
from guard.services.istio.validators.latency import IstioLatencyValidator

__all__ = [
    "IstioErrorRateValidator",
    "IstioLatencyValidator",
]
