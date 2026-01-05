"""Thanos service configuration and constants."""

from dataclasses import dataclass, field


@dataclass
class ThanosComponentConfig:
    """Configuration for a Thanos component."""

    name: str
    label_selectors: list[str] = field(default_factory=list)
    is_required: bool = False
    http_port: int = 10902
    ready_endpoint: str = "/-/ready"
    health_endpoint: str = "/-/healthy"

    def __post_init__(self) -> None:
        """Generate default label selectors if none provided."""
        if not self.label_selectors:
            self.label_selectors = [
                f"app.kubernetes.io/name={self.name}",
                f"app={self.name}",
                f"app.kubernetes.io/component={self.name.replace('thanos-', '')}",
            ]


@dataclass
class ThanosServiceConfig:
    """Configuration for Thanos service operations.

    This configuration allows customization of namespaces, label selectors,
    and component settings for different Helm chart conventions.
    """

    namespace: str = "monitoring"
    components: dict[str, ThanosComponentConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize default component configurations."""
        if not self.components:
            self.components = {
                "thanos-query": ThanosComponentConfig(
                    name="thanos-query",
                    is_required=True,
                    http_port=10902,
                    label_selectors=[
                        "app.kubernetes.io/name=thanos-query",
                        "app=thanos-query",
                        "app.kubernetes.io/component=query",
                    ],
                ),
                "thanos-store": ThanosComponentConfig(
                    name="thanos-store",
                    is_required=True,
                    http_port=10902,
                    label_selectors=[
                        "app.kubernetes.io/name=thanos-store",
                        "app=thanos-store",
                        "app.kubernetes.io/component=store",
                        "app.kubernetes.io/component=storegateway",
                    ],
                ),
                "thanos-compactor": ThanosComponentConfig(
                    name="thanos-compactor",
                    is_required=False,
                    http_port=10902,
                    label_selectors=[
                        "app.kubernetes.io/name=thanos-compactor",
                        "app=thanos-compactor",
                        "app.kubernetes.io/component=compactor",
                    ],
                ),
                "thanos-query-frontend": ThanosComponentConfig(
                    name="thanos-query-frontend",
                    is_required=False,
                    http_port=10902,
                    label_selectors=[
                        "app.kubernetes.io/name=thanos-query-frontend",
                        "app=thanos-query-frontend",
                        "app.kubernetes.io/component=query-frontend",
                    ],
                ),
                "thanos-ruler": ThanosComponentConfig(
                    name="thanos-ruler",
                    is_required=False,
                    http_port=10902,
                ),
                "thanos-receive": ThanosComponentConfig(
                    name="thanos-receive",
                    is_required=False,
                    http_port=10902,
                ),
            }

    def get_component(self, name: str) -> ThanosComponentConfig | None:
        """Get component configuration by name."""
        return self.components.get(name)

    def get_required_components(self) -> list[str]:
        """Get list of required component names."""
        return [name for name, cfg in self.components.items() if cfg.is_required]


# Default configuration instance
DEFAULT_THANOS_CONFIG = ThanosServiceConfig()


@dataclass
class ThanosValidationThresholds:
    """Validation thresholds for Thanos upgrades.

    These thresholds define acceptable limits for Thanos
    performance metrics during and after upgrades.
    """

    # Query latency thresholds (seconds)
    query_latency_p95_max: float = 5.0
    query_latency_p99_max: float = 10.0

    # Store API thresholds
    store_api_latency_p95_max: float = 2.0

    # Compaction thresholds
    compaction_failures_max: int = 0
    blocks_loaded_min: int = 1

    # Query frontend thresholds
    query_range_latency_p95_max: float = 10.0

    # Resource thresholds
    memory_increase_percent_max: float = 50.0
    cpu_increase_percent_max: float = 50.0


# Default Thanos metrics for monitoring
THANOS_METRIC_AGGREGATIONS = {
    # Query performance
    "thanos.query.api.instant.latency.p95": {
        "query": "avg:thanos_query_api_instant_query_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 instant query latency",
    },
    "thanos.query.api.range.latency.p95": {
        "query": "avg:thanos_query_api_range_query_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 range query latency",
    },
    # Store performance
    "thanos.store.bucket.latency.p95": {
        "query": "avg:thanos_bucket_store_series_get_all_duration_seconds.quantile{quantile:0.95,$cluster}",
        "aggregation": "avg",
        "description": "P95 bucket store series retrieval latency",
    },
    "thanos.store.blocks.loaded": {
        "query": "sum:thanos_bucket_store_blocks_loaded{$cluster}",
        "aggregation": "sum",
        "description": "Number of blocks loaded in store",
    },
    # Compactor metrics
    "thanos.compactor.runs.total": {
        "query": "sum:thanos_compact_group_compactions_total{$cluster}",
        "aggregation": "sum",
        "description": "Total compaction runs",
    },
    "thanos.compactor.failures.total": {
        "query": "sum:thanos_compact_group_compactions_failures_total{$cluster}",
        "aggregation": "sum",
        "description": "Total compaction failures",
    },
    # Query gate metrics
    "thanos.query.gate.queries.inflight": {
        "query": "avg:thanos_query_gate_queries_in_flight{$cluster}",
        "aggregation": "avg",
        "description": "Queries currently in flight",
    },
    "thanos.query.gate.queries.max": {
        "query": "avg:thanos_query_gate_queries_max{$cluster}",
        "aggregation": "avg",
        "description": "Maximum concurrent queries allowed",
    },
}

# Thanos components to monitor
THANOS_COMPONENTS = [
    "thanos-query",
    "thanos-query-frontend",
    "thanos-store",
    "thanos-compactor",
    "thanos-ruler",
    "thanos-receive",
]

# Default namespace for Thanos
DEFAULT_THANOS_NAMESPACE = "monitoring"
