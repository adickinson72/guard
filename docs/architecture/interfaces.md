# Interface Contracts

This document describes all interface contracts in GUARD.

## External Service Interfaces

### CloudProvider

**Purpose**: Abstract cloud operations (AWS, GCP, Azure)

**Key Methods**:
- `assume_role(role_arn, session_name)` - Assume IAM role
- `get_secret(secret_name)` - Retrieve secrets
- `get_cluster_info(cluster_name)` - Get cluster metadata
- `generate_cluster_token(cluster_name)` - Generate auth token
- `list_clusters(region)` - List clusters

**Implementation**: `AWSAdapter` (wraps boto3)

**Future**: GCPAdapter, AzureAdapter

---

### KubernetesProvider

**Purpose**: Abstract Kubernetes operations

**Key Methods**:
- `get_nodes()` - Get all nodes (returns normalized `NodeInfo`)
- `check_nodes_ready()` - Check node readiness
- `get_pods(namespace, label_selector)` - Get pods
- `check_pods_ready(namespace, label_selector)` - Check pod readiness
- `get_deployment(name, namespace)` - Get deployment info
- `restart_deployment/daemonset/statefulset()` - Restart workloads

**Implementation**: `KubernetesAdapter` (wraps kubernetes Python client)

**Future**: Could use kubectl subprocess instead

---

### MetricsProvider

**Purpose**: Abstract metrics query operations

**Key Methods**:
- `query_timeseries(metric_name, start_time, end_time, tags)` - Query time-series data
- `query_scalar(...)` - Query single value
- `query_statistics(...)` - Get min/max/avg/last
- `check_active_alerts(tags)` - Check for active alerts
- `query_raw(query, start_time, end_time)` - Escape hatch for provider-specific queries

**Implementation**: `DatadogAdapter` (wraps datadog-api-client)

**Future**: PrometheusAdapter

---

### GitOpsProvider

**Purpose**: Abstract version control operations

**Key Methods**:
- `create_branch(project_id, branch_name, ref)` - Create branch
- `get_file_content(project_id, file_path, ref)` - Get file
- `update_file(project_id, file_path, content, message, branch)` - Update/create file
- `create_merge_request(...)` - Create MR/PR
- `add_merge_request_comment(...)` - Add comment

**Implementation**: `GitLabAdapter` (wraps python-gitlab)

**Future**: GitHubAdapter

---

### StateStore

**Purpose**: Abstract state persistence

**Key Methods**:
- `save_cluster(cluster)` - Save cluster config
- `get_cluster(cluster_id)` - Get cluster config
- `list_clusters(batch_id, status)` - List with filters
- `update_cluster_status(cluster_id, status, metadata)` - Update status
- `query_by_batch(batch_id)` - Query batch

**Implementation**: `DynamoDBAdapter` (wraps boto3 DynamoDB)

**Future**: PostgresAdapter, RedisAdapter

## Internal System Interfaces

### Check

**Purpose**: Define health check contract

**Key Methods**:
- `execute(cluster, context)` - Run the check
- Properties: `name`, `description`, `is_critical`, `timeout_seconds`

**Implementations**:
- Generic: `ControlPlaneHealthCheck`, `NodeReadinessCheck`, `PodHealthCheck`
- Istio: `IstioCtlAnalyzeCheck`, `IstioSidecarVersionCheck`

---

### Validator

**Purpose**: Define post-upgrade validation contract

**Key Methods**:
- `validate(cluster, baseline, current, thresholds)` - Validate upgrade
- `get_required_metrics()` - List required metric names
- Properties: `name`, `description`, `is_critical`, `timeout_seconds`

**Implementations**:
- Istio: `IstioLatencyValidator`, `IstioErrorRateValidator`

---

### ConfigUpdater

**Purpose**: Define GitOps config update contract

**Key Methods**:
- `update_version(file_path, target_version, backup)` - Update version
- `get_current_version(file_path)` - Get current version
- `validate_config(file_path)` - Validate syntax
- `supports_file(file_path)` - Check if updater handles file

**Implementations**:
- `IstioHelmUpdater` - Updates Flux HelmRelease YAML

## Contract Testing

Every interface has contract tests that implementations must pass:

```python
# tests/contracts/test_metrics_provider_contract.py
class MetricsProviderContract:
    """Contract tests that all MetricsProvider implementations must pass."""

    @pytest.fixture
    def provider(self):
        """Subclass provides concrete implementation."""
        raise NotImplementedError

    async def test_query_scalar_returns_float(self, provider):
        result = await provider.query_scalar(...)
        assert isinstance(result, float)

    async def test_query_timeseries_returns_list(self, provider):
        result = await provider.query_timeseries(...)
        assert isinstance(result, list)
        assert all(isinstance(p, MetricPoint) for p in result)
```

Implementations inherit contract:

```python
class TestDatadogAdapter(MetricsProviderContract):
    @pytest.fixture
    def provider(self):
        return DatadogAdapter(api_key="test", app_key="test")
```

This ensures substitutability (Liskov Substitution Principle).
