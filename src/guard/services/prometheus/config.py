"""Prometheus service configuration and constants."""

from dataclasses import dataclass, field


@dataclass
class PrometheusComponentConfig:
    """Configuration for a Prometheus component."""

    name: str
    label_selectors: list[str] = field(default_factory=list)
    is_required: bool = False
    http_port: int = 9090
    ready_endpoint: str = "/-/ready"
    health_endpoint: str = "/-/healthy"

    def __post_init__(self) -> None:
        """Generate default label selectors if none provided."""
        if not self.label_selectors:
            self.label_selectors = [
                f"app.kubernetes.io/name={self.name}",
                f"app={self.name}",
                f"app.kubernetes.io/component={self.name.replace('prometheus-', '')}",
            ]


@dataclass
class PrometheusServiceConfig:
    """Configuration for Prometheus service operations.

    This configuration allows customization of namespaces, label selectors,
    and component settings for different Helm chart conventions.
    """

    namespace: str = "monitoring"
    components: dict[str, PrometheusComponentConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize default component configurations."""
        if not self.components:
            self.components = {
                "prometheus-server": PrometheusComponentConfig(
                    name="prometheus-server",
                    is_required=True,
                    http_port=9090,
                    label_selectors=[
                        "app.kubernetes.io/name=prometheus",
                        "app.kubernetes.io/name=prometheus-server",
                        "app=prometheus-server",
                        "app=prometheus",
                    ],
                ),
                "prometheus-alertmanager": PrometheusComponentConfig(
                    name="prometheus-alertmanager",
                    is_required=False,
                    http_port=9093,
                    label_selectors=[
                        "app.kubernetes.io/name=alertmanager",
                        "app.kubernetes.io/name=prometheus-alertmanager",
                        "app=alertmanager",
                        "app=prometheus-alertmanager",
                    ],
                ),
                "prometheus-pushgateway": PrometheusComponentConfig(
                    name="prometheus-pushgateway",
                    is_required=False,
                    http_port=9091,
                ),
                "prometheus-node-exporter": PrometheusComponentConfig(
                    name="prometheus-node-exporter",
                    is_required=False,
                    http_port=9100,
                    label_selectors=[
                        "app.kubernetes.io/name=prometheus-node-exporter",
                        "app=prometheus-node-exporter",
                        "app=node-exporter",
                    ],
                ),
            }

    def get_component(self, name: str) -> PrometheusComponentConfig | None:
        """Get component configuration by name."""
        return self.components.get(name)

    def get_required_components(self) -> list[str]:
        """Get list of required component names."""
        return [name for name, cfg in self.components.items() if cfg.is_required]


# Default configuration instance
DEFAULT_PROMETHEUS_CONFIG = PrometheusServiceConfig()

# Default namespace for Prometheus (for backward compatibility)
DEFAULT_PROMETHEUS_NAMESPACE = "monitoring"

# Prometheus components to monitor (for backward compatibility)
PROMETHEUS_COMPONENTS = [
    "prometheus-server",
    "prometheus-alertmanager",
    "prometheus-pushgateway",
    "prometheus-node-exporter",
]

# Default Prometheus metrics for monitoring
PROMETHEUS_METRIC_AGGREGATIONS = {
    # Query performance
    "prometheus.query.latency.p95": {
        "query": "avg:prometheus_engine_query_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 query latency",
    },
    "prometheus.query.latency.p99": {
        "query": "avg:prometheus_engine_query_duration_seconds.quantile{quantile:0.99,$cluster}",
        "aggregation": "avg",
        "description": "P99 query latency",
    },
    # TSDB metrics
    "prometheus.tsdb.head.series": {
        "query": "avg:prometheus_tsdb_head_series{$cluster}",
        "aggregation": "avg",
        "description": "Active time series count",
    },
    "prometheus.tsdb.head.chunks": {
        "query": "avg:prometheus_tsdb_head_chunks{$cluster}",
        "aggregation": "avg",
        "description": "Head chunks count",
    },
    "prometheus.tsdb.compaction.duration": {
        "query": "avg:prometheus_tsdb_compaction_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 compaction duration",
    },
    # Scrape metrics
    "prometheus.scrape.targets.up": {
        "query": "sum:up{$cluster}",
        "aggregation": "sum",
        "description": "Number of up targets",
    },
    "prometheus.scrape.duration.p95": {
        "query": "avg:prometheus_target_scrape_pool_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 scrape duration",
    },
    # Resource utilization
    "prometheus.memory.usage": {
        "query": "avg:process_resident_memory_bytes{service:prometheus,$cluster}",
        "aggregation": "avg",
        "description": "Memory usage in bytes",
    },
    "prometheus.cpu.usage": {
        "query": "avg:process_cpu_seconds_total{service:prometheus,$cluster}.as_rate()",
        "aggregation": "avg",
        "description": "CPU usage rate",
    },
}
