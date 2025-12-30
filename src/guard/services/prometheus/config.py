"""Prometheus service configuration and constants."""

# Default namespace for Prometheus
DEFAULT_PROMETHEUS_NAMESPACE = "monitoring"

# Prometheus components to monitor
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
