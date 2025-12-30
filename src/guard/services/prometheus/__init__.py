"""Prometheus service module.

Provides Prometheus-specific upgrade operations including:
- Health checks for server, alertmanager, and node-exporter
- Query latency and scrape health validation
- Helm chart updates via Flux

Usage:
    from guard.services.prometheus import PrometheusService

    service = PrometheusService()
    result = await service.validate_deployment(cluster, k8s_provider)
"""

from guard.services.prometheus.prometheus_service import PrometheusService

__all__ = [
    "PrometheusService",
]
