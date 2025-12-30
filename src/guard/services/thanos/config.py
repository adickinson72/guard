"""Thanos service configuration and constants."""

from dataclasses import dataclass


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
