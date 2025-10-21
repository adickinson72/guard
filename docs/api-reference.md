# API Reference

This document provides a reference for GUARD's Python API. While GUARD is primarily used via the CLI, you can also use it as a library in your own Python code.

## Table of Contents

- [Installation](#installation)
- [Core Modules](#core-modules)
- [Configuration](#configuration)
- [Cluster Registry](#cluster-registry)
- [Pre-Check Engine](#pre-check-engine)
- [Validation Engine](#validation-engine)
- [GitOps Manager](#gitops-manager)
- [Rollback Engine](#rollback-engine)
- [Clients](#clients)
- [Models](#models)
- [Exceptions](#exceptions)

## Installation

```bash
pip install guard
```

## Core Modules

### Configuration

Load and manage GUARD configuration.

```python
from guard.core.config import GuardConfig

# Load from file
config = GuardConfig.from_file("~/.guard/config.yaml")

# Access configuration
print(config.aws.region)
print(config.gitlab.url)
print(config.validation.soak_period_minutes)

# Get batch configuration
batch = config.get_batch("prod-wave-1")
print(batch.clusters)
```

**Class**: `GuardConfig`

**Methods**:
- `from_file(path: str | Path) -> GuardConfig` - Load configuration from YAML file
- `get_batch(batch_name: str) -> BatchConfig | None` - Get batch configuration by name
- `to_dict() -> dict[str, Any]` - Convert to dictionary

**Attributes**:
- `aws: AWSConfig` - AWS configuration
- `gitlab: GitLabConfig` - GitLab configuration
- `datadog: DatadogConfig` - Datadog configuration
- `validation: ValidationConfig` - Validation settings
- `rollback: RollbackConfig` - Rollback settings
- `llm: LLMConfig` - LLM settings
- `batches: list[BatchConfig]` - Batch definitions
- `logging: LoggingConfig` - Logging configuration

## Cluster Registry

Query and manage cluster metadata.

```python
from guard.registry.cluster_registry import ClusterRegistry

# Initialize
registry = ClusterRegistry(table_name="guard-cluster-registry")

# Get all clusters in a batch
clusters = registry.get_clusters_by_batch("prod-wave-1")
for cluster in clusters:
    print(f"{cluster.cluster_id}: {cluster.current_istio_version}")

# Get specific cluster
cluster = registry.get_cluster("eks-prod-us-east-1-api")
print(f"Environment: {cluster.environment}")
print(f"Region: {cluster.region}")

# Update cluster status
registry.update_cluster_status("eks-prod-us-east-1-api", "upgrading")

# Update cluster version
registry.update_cluster_version("eks-prod-us-east-1-api", "1.20.0")
```

**Class**: `ClusterRegistry`

**Methods**:
- `__init__(table_name: str) -> None`
- `get_clusters_by_batch(batch_id: str) -> list[Cluster]`
- `get_cluster(cluster_id: str) -> Cluster`
- `update_cluster_status(cluster_id: str, status: str) -> None`
- `update_cluster_version(cluster_id: str, version: str) -> None`
- `list_all_clusters() -> list[Cluster]`

## Pre-Check Engine

Run health checks before upgrades.

```python
from guard.checks.pre_check_engine import PreCheckEngine
from guard.core.config import GuardConfig

# Initialize
config = GuardConfig.from_file("~/.guard/config.yaml")
engine = PreCheckEngine(config=config)

# Run pre-checks for clusters
clusters = registry.get_clusters_by_batch("prod-wave-1")
results = await engine.run_pre_checks(clusters)

# Process results
for cluster_id, checks in results.items():
    print(f"\nCluster: {cluster_id}")
    for check in checks:
        status_icon = "✓" if check.status == "PASS" else "✗"
        print(f"  {status_icon} {check.check_name}: {check.message}")
```

**Class**: `PreCheckEngine`

**Methods**:
- `__init__(config: GuardConfig) -> None`
- `async run_pre_checks(clusters: list[Cluster]) -> dict[str, list[HealthCheckResult]]`
- `async check_kubernetes_health(cluster: Cluster) -> HealthCheckResult`
- `async check_istio_health(cluster: Cluster) -> HealthCheckResult`
- `async check_datadog_metrics(cluster: Cluster) -> HealthCheckResult`
- `async check_active_alerts(cluster: Cluster) -> HealthCheckResult`

## Validation Engine

Validate upgrades and compare metrics.

```python
from guard.validation.engine import ValidationEngine
from guard.core.config import GuardConfig

# Initialize
config = GuardConfig.from_file("~/.guard/config.yaml")
engine = ValidationEngine(config=config)

# Run validation
cluster = registry.get_cluster("eks-prod-us-east-1-api")
result = await engine.validate_upgrade(
    cluster=cluster,
    baseline_metrics=baseline,
    soak_period_minutes=60
)

# Check result
if result.passed:
    print("Validation passed!")
else:
    print("Validation failed:")
    for violation in result.threshold_violations:
        print(f"  - {violation}")
```

**Class**: `ValidationEngine`

**Methods**:
- `__init__(config: GuardConfig) -> None`
- `async validate_upgrade(cluster: Cluster, baseline_metrics: dict, soak_period_minutes: int) -> ValidationResult`
- `async wait_for_flux_sync(cluster: Cluster, timeout_minutes: int) -> bool`
- `async monitor_rollout(cluster: Cluster) -> bool`
- `async query_post_upgrade_metrics(cluster: Cluster) -> dict[str, float]`

## GitOps Manager

Create and manage GitLab merge requests.

```python
from guard.gitops.manager import GitOpsManager
from guard.core.config import GuardConfig

# Initialize
config = GuardConfig.from_file("~/.guard/config.yaml")
manager = GitOpsManager(config=config)

# Create upgrade MR
clusters = registry.get_clusters_by_batch("prod-wave-1")
health_report = "All checks passed"

mr = await manager.create_upgrade_mr(
    clusters=clusters,
    target_version="1.20.0",
    health_report=health_report
)

print(f"MR created: {mr['web_url']}")
```

**Class**: `GitOpsManager`

**Methods**:
- `__init__(config: GuardConfig) -> None`
- `async create_upgrade_mr(clusters: list[Cluster], target_version: str, health_report: str) -> dict`
- `async create_rollback_mr(cluster: Cluster, previous_version: str) -> dict`
- `async update_flux_config(cluster: Cluster, new_version: str) -> None`

## Rollback Engine

Handle automated rollbacks.

```python
from guard.rollback.engine import RollbackEngine
from guard.core.config import GuardConfig

# Initialize
config = GuardConfig.from_file("~/.guard/config.yaml")
engine = RollbackEngine(config=config)

# Trigger rollback
cluster = registry.get_cluster("eks-prod-us-east-1-api")
result = await engine.rollback(
    cluster=cluster,
    previous_version="1.19.3",
    failure_reason="Validation failed: latency increased 25%"
)

print(f"Rollback MR: {result['mr_url']}")
```

**Class**: `RollbackEngine`

**Methods**:
- `__init__(config: GuardConfig) -> None`
- `async rollback(cluster: Cluster, previous_version: str, failure_reason: str) -> dict`
- `async analyze_failure(cluster: Cluster, validation_result: ValidationResult) -> str` (if LLM enabled)

## Clients

### AWS Client

```python
from guard.clients.aws_client import AWSClient

client = AWSClient(region="us-east-1")

# Assume role for cluster access
credentials = await client.assume_role(
    role_arn="arn:aws:iam::123:role/GUARD-EKSAccess",
    session_name="guard-session"
)

# Get secret
secret = await client.get_secret("guard/gitlab-token")
```

**Methods**:
- `async assume_role(role_arn: str, session_name: str) -> dict`
- `async get_secret(secret_name: str) -> str | dict`
- `async describe_cluster(cluster_name: str) -> dict`

### Kubernetes Client

```python
from guard.clients.kubernetes_client import KubernetesClient

client = KubernetesClient(cluster_name="eks-prod-us-east-1-api")

# Get pod status
pods = await client.get_pods(namespace="istio-system")
for pod in pods:
    print(f"{pod.name}: {pod.status}")

# Check rollout status
ready = await client.is_deployment_ready(
    namespace="istio-system",
    deployment="istiod"
)
```

**Methods**:
- `async get_pods(namespace: str) -> list[Pod]`
- `async is_deployment_ready(namespace: str, deployment: str) -> bool`
- `async get_events(namespace: str) -> list[Event]`

### Datadog Client

```python
from guard.clients.datadog_client import DatadogClient

client = DatadogClient(
    api_key="xxx",
    app_key="xxx",
    site="datadoghq.com"
)

# Query metrics
metrics = await client.query_metrics(
    query="avg:kubernetes.cpu.usage{cluster_name:eks-prod}",
    start_time=int(time.time()) - 3600,
    end_time=int(time.time())
)

# Check for active alerts
alerts = await client.get_active_monitors(tags=["cluster:eks-prod"])
```

**Methods**:
- `async query_metrics(query: str, start_time: int, end_time: int) -> dict`
- `async get_active_monitors(tags: list[str]) -> list[dict]`

### GitLab Client

```python
from guard.clients.gitlab_client import GitLabClient

client = GitLabClient(
    url="https://gitlab.company.com",
    token="glpat-xxx"
)

# Create MR
mr = await client.create_merge_request(
    project_id="infra/k8s-clusters",
    source_branch="guard/upgrade-1.20.0",
    target_branch="main",
    title="Upgrade Istio to 1.20.0",
    description="Automated upgrade via GUARD"
)
```

**Methods**:
- `async create_merge_request(project_id: str, source_branch: str, target_branch: str, title: str, description: str) -> dict`
- `async create_branch(project_id: str, branch_name: str, ref: str) -> dict`
- `async commit_files(project_id: str, branch: str, files: list[dict], message: str) -> dict`

## Models

### Cluster

```python
from guard.core.models import Cluster

cluster = Cluster(
    cluster_id="eks-prod-us-east-1-api",
    batch_id="prod-wave-1",
    environment="production",
    region="us-east-1",
    gitlab_repo="infra/k8s-clusters",
    flux_config_path="clusters/prod/api/istio.yaml",
    aws_role_arn="arn:aws:iam::123:role/GUARD-Access",
    current_istio_version="1.19.3",
    datadog_tags={"cluster": "eks-prod", "env": "prod"},
    owner_team="platform",
    owner_handle="@platform",
    status="healthy"
)
```

**Attributes**:
- `cluster_id: str` - Unique cluster identifier
- `batch_id: str` - Batch this cluster belongs to
- `environment: str` - Environment (dev, staging, prod)
- `region: str` - AWS region
- `gitlab_repo: str` - GitLab repository path
- `flux_config_path: str` - Path to Flux HelmRelease YAML
- `aws_role_arn: str` - IAM role for cluster access
- `current_istio_version: str` - Current Istio version
- `datadog_tags: dict[str, str]` - Tags for Datadog queries
- `owner_team: str` - Owning team
- `owner_handle: str` - Notification handle
- `status: str` - Current status

### HealthCheckResult

```python
from guard.core.models import HealthCheckResult, CheckStatus

result = HealthCheckResult(
    cluster_id="eks-prod-us-east-1-api",
    check_name="kubernetes_health",
    status=CheckStatus.PASS,
    message="Kubernetes API healthy",
    timestamp=datetime.now(),
    details={"api_version": "1.28"}
)
```

**Attributes**:
- `cluster_id: str`
- `check_name: str`
- `status: CheckStatus` - PASS, FAIL, WARN
- `message: str`
- `timestamp: datetime`
- `details: dict[str, Any]`

### ValidationResult

```python
from guard.core.models import ValidationResult

result = ValidationResult(
    cluster_id="eks-prod-us-east-1-api",
    passed=True,
    metrics={
        "latency_p95": 245.5,
        "error_rate": 0.02,
        "cpu_usage": 45.3
    },
    threshold_violations=[]
)
```

**Attributes**:
- `cluster_id: str`
- `passed: bool`
- `metrics: dict[str, float]`
- `threshold_violations: list[str]`

## Exceptions

```python
from guard.core.exceptions import (
    ConfigurationError,
    RegistryError,
    HealthCheckError,
    ValidationError,
    GitOpsError,
    RollbackError
)

try:
    config = GuardConfig.from_file("config.yaml")
except ConfigurationError as e:
    print(f"Configuration error: {e}")

try:
    cluster = registry.get_cluster("invalid-id")
except RegistryError as e:
    print(f"Registry error: {e}")
```

**Exception Hierarchy**:
- `GuardError` (base exception)
  - `ConfigurationError` - Configuration issues
  - `RegistryError` - Cluster registry errors
  - `HealthCheckError` - Pre-check failures
  - `ValidationError` - Post-upgrade validation failures
  - `GitOpsError` - GitLab/GitOps errors
  - `RollbackError` - Rollback failures
  - `ClientError` - External service client errors

## Complete Example

```python
import asyncio
from guard.core.config import GuardConfig
from guard.registry.cluster_registry import ClusterRegistry
from guard.checks.pre_check_engine import PreCheckEngine
from guard.gitops.manager import GitOpsManager
from guard.validation.engine import ValidationEngine

async def main():
    # Load configuration
    config = GuardConfig.from_file("~/.guard/config.yaml")

    # Initialize components
    registry = ClusterRegistry(table_name=config.aws.dynamodb.table_name)
    pre_check_engine = PreCheckEngine(config=config)
    gitops_manager = GitOpsManager(config=config)
    validation_engine = ValidationEngine(config=config)

    # Get clusters
    batch_id = "prod-wave-1"
    target_version = "1.20.0"
    clusters = registry.get_clusters_by_batch(batch_id)

    # Run pre-checks
    print(f"Running pre-checks for {len(clusters)} clusters...")
    check_results = await pre_check_engine.run_pre_checks(clusters)

    all_passed = all(
        all(check.status == "PASS" for check in checks)
        for checks in check_results.values()
    )

    if not all_passed:
        print("Pre-checks failed!")
        return

    # Create upgrade MR
    print("Creating upgrade MR...")
    health_report = format_health_report(check_results)
    mr = await gitops_manager.create_upgrade_mr(
        clusters=clusters,
        target_version=target_version,
        health_report=health_report
    )
    print(f"MR created: {mr['web_url']}")

    # Wait for user to merge MR
    input("Press Enter after merging MR...")

    # Validate upgrade
    print("Validating upgrade...")
    for cluster in clusters:
        # Get baseline metrics from pre-check results
        baseline = extract_baseline_metrics(check_results[cluster.cluster_id])

        # Run validation
        result = await validation_engine.validate_upgrade(
            cluster=cluster,
            baseline_metrics=baseline,
            soak_period_minutes=60
        )

        if result.passed:
            print(f"✓ {cluster.cluster_id}: Validation passed")
            registry.update_cluster_status(cluster.cluster_id, "healthy")
            registry.update_cluster_version(cluster.cluster_id, target_version)
        else:
            print(f"✗ {cluster.cluster_id}: Validation failed")
            print(f"Violations: {result.threshold_violations}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Type Hints

GUARD is fully type-annotated. Use with mypy for type checking:

```bash
pip install mypy
mypy your_script.py
```

## Logging

Configure logging in your application:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# GUARD loggers
logging.getLogger('guard').setLevel(logging.DEBUG)
```
