# Architecture Documentation

This document describes the architecture, design decisions, and implementation details of GUARD (GitOps Upgrade Automation with Rollback Detection).

## Table of Contents

- [High-Level Overview](#high-level-overview)
- [System Architecture](#system-architecture)
- [Component Details](#component-details)
- [Workflow Phases](#workflow-phases)
- [State Management](#state-management)
- [Data Flow](#data-flow)
- [Design Decisions](#design-decisions)
- [Extension Points](#extension-points)

## High-Level Overview

GUARD is a Python-based automation tool that orchestrates safe, progressive Istio upgrades across multiple EKS clusters using GitOps workflows.

### Key Principles

1. **Safety First**: Human-in-the-loop gates for critical operations
2. **Fail-Fast**: Comprehensive pre-checks before any changes
3. **GitOps Native**: All changes via GitLab merge requests
4. **Observable**: Rich metrics and logging throughout
5. **Resumable**: Stateful execution with DynamoDB persistence

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer                                                   │
│  • Command parsing and user interaction                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Core Engine Layer                                           │
│  • Pre-Check Engine      • Validation Engine                │
│  • GitOps Manager        • Rollback Engine                  │
│  • State Manager         • LLM Analyzer (optional)          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  Integration Layer                                           │
│  • AWS Client (STS, EKS, Secrets Manager, DynamoDB)         │
│  • Kubernetes Client (kubectl wrapper)                      │
│  • Datadog Client (metrics, monitors, events)               │
│  • GitLab Client (MRs, branches, commits)                   │
│  • Istioctl Wrapper (analyze, version)                      │
└──────────────────────────────────────────────────────────────┘
```

## System Architecture

### Component Diagram

```
┌──────────────┐
│   User/CI    │
└──────┬───────┘
       │
       │ guard run --batch prod-wave-1 --target-version 1.20.0
       │
┌──────▼──────────────────────────────────────────────────────┐
│  CLI (src/guard/cli/main.py)                                  │
│  • Argument parsing                                          │
│  • Command routing                                           │
│  • Output formatting                                         │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│  Core Configuration (src/guard/core/config.py)                │
│  • Load YAML config                                          │
│  • Validate settings                                         │
│  • Provide typed access to configuration                    │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│  Cluster Registry (src/guard/registry/cluster_registry.py)    │
│  • Query DynamoDB for cluster metadata                      │
│  • Filter clusters by batch                                 │
│  • Update cluster state                                     │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│  Pre-Check Engine (src/guard/checks/pre_check_engine.py)      │
│  • Run health checks on each cluster:                       │
│    - Kubernetes API health                                  │
│    - Istio control plane health (istioctl analyze)          │
│    - Datadog metrics baseline                               │
│    - Active alert detection                                 │
│  • Fail-fast on any check failure                           │
└──────┬──────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│  GitOps Manager (src/guard/gitops/manager.py)                 │
│  • Clone GitLab repository                                  │
│  • Create feature branch                                    │
│  • Update Flux HelmRelease configs                          │
│  • Create merge request with health report                  │
└──────┬──────────────────────────────────────────────────────┘
       │
       │ [User manually reviews and merges MR]
       │
       │ guard monitor --batch prod-wave-1
       │
┌──────▼──────────────────────────────────────────────────────┐
│  Validation Engine (src/guard/validation/engine.py)           │
│  • Wait for Flux sync                                       │
│  • Monitor pod rollout                                      │
│  • Soak period                                              │
│  • Compare metrics (pre vs post)                            │
│  • Validate against thresholds                              │
└──────┬──────────────────────────────────────────────────────┘
       │
       │ [On failure]
       │
┌──────▼──────────────────────────────────────────────────────┐
│  Rollback Engine (src/guard/rollback/engine.py)               │
│  • Create rollback MR (revert version)                      │
│  • Optional: LLM analysis of failure                        │
│  • Send notifications (Slack, PagerDuty)                    │
└──────────────────────────────────────────────────────────────┘
```

## Component Details

### CLI Layer

**Location**: `src/guard/cli/main.py`

Handles user interaction and command routing.

**Commands**:
- `guard validate` - Validate configuration
- `guard list` - List clusters
- `guard run` - Execute upgrade workflow
- `guard monitor` - Monitor upgrade progress
- `guard rollback` - Trigger manual rollback
- `guard registry` - Manage cluster registry

### Core Models

**Location**: `src/guard/core/models.py`

Defines core data structures:

```python
@dataclass
class Cluster:
    cluster_id: str
    batch_id: str
    environment: str
    region: str
    gitlab_repo: str
    flux_config_path: str
    aws_role_arn: str
    current_istio_version: str
    datadog_tags: dict[str, str]

@dataclass
class HealthCheckResult:
    cluster_id: str
    check_name: str
    status: CheckStatus  # PASS, FAIL, WARN
    message: str
    timestamp: datetime
    details: dict[str, Any]

@dataclass
class ValidationResult:
    cluster_id: str
    passed: bool
    metrics: dict[str, float]
    threshold_violations: list[str]
```

### Cluster Registry

**Location**: `src/guard/registry/cluster_registry.py`

Manages cluster metadata in DynamoDB.

**Key Methods**:
- `get_clusters_by_batch(batch_id: str) -> list[Cluster]`
- `update_cluster_status(cluster_id: str, status: str)`
- `get_cluster(cluster_id: str) -> Cluster`

**DynamoDB Schema**:
- Partition Key: `cluster_id`
- GSI: `batch_id-index` for batch queries

### Pre-Check Engine

**Location**: `src/guard/checks/pre_check_engine.py`

Runs comprehensive health checks before upgrades.

**Checks**:
1. **Kubernetes Health**
   - Control plane API availability
   - Node status
   - Critical pod health

2. **Istio Health**
   - `istioctl analyze` validation
   - Pilot/proxy versions
   - Configuration errors

3. **Datadog Metrics**
   - Baseline latency (p95, p99)
   - Error rates
   - Resource usage
   - Active alerts

**Interface**:
```python
class PreCheckEngine:
    async def run_pre_checks(
        self,
        clusters: list[Cluster],
        config: GuardConfig
    ) -> dict[str, list[HealthCheckResult]]:
        """Run all pre-checks for a list of clusters."""
```

### GitOps Manager

**Location**: `src/guard/gitops/manager.py`

Manages GitLab operations.

**Workflow**:
1. Clone repository
2. Create branch: `guard/upgrade-istio-{version}-{batch}-{timestamp}`
3. Update Flux HelmRelease files
4. Create commit
5. Push branch
6. Create MR with health report

**Flux Config Updates**:
```python
# src/guard/gitops/flux_config.py
def update_istio_version(
    file_path: Path,
    new_version: str
) -> None:
    """Update Istio version in Flux HelmRelease YAML."""
```

### Validation Engine

**Location**: `src/guard/validation/engine.py`

Post-upgrade validation and monitoring.

**Process**:
1. Wait for Flux sync (poll GitOps status)
2. Monitor pod rollout (`kubectl rollout status`)
3. Soak period (configurable wait)
4. Query post-upgrade metrics
5. Compare with baseline
6. Validate against thresholds

**Metrics Comparison**:
```python
# src/guard/validation/metrics_comparator.py
class MetricsComparator:
    def compare(
        self,
        baseline: dict[str, float],
        current: dict[str, float],
        thresholds: ValidationThresholdsConfig
    ) -> ValidationResult:
        """Compare metrics and check thresholds."""
```

### Rollback Engine

**Location**: `src/guard/rollback/engine.py`

Automated rollback on validation failure.

**Actions**:
1. Create rollback MR (revert to previous version)
2. Optional: Run LLM analysis
3. Send notifications
4. Update cluster state

### State Management

**Location**: `src/guard/registry/cluster_registry.py`

All state stored in DynamoDB for resumability.

**State Transitions**:
```
healthy → pre_check_running → pre_check_passed → mr_created →
mr_merged → upgrading → validating → upgraded

                                    ↓ (on failure)
                              rollback_needed → rollback_mr_created →
                              rollback_completed → healthy
```

## Workflow Phases

### Phase 0: Setup

**Goal**: Initialize environment

**Steps**:
1. Load configuration
2. Validate AWS credentials
3. Retrieve secrets from Secrets Manager
4. Initialize clients (AWS, Kubernetes, Datadog, GitLab)

### Phase 1: Pre-Upgrade Checks

**Goal**: Ensure clusters are healthy before upgrade

**Steps**:
1. Query cluster registry for batch
2. For each cluster in batch:
   - Assume AWS role
   - Connect to EKS
   - Run Kubernetes health checks
   - Run Istio health checks
   - Query Datadog metrics (baseline)
   - Check for active alerts
3. Aggregate results
4. Fail-fast if any check fails

**Output**: Health report with all check results

### Phase 2: GitOps Change

**Goal**: Create MR with upgrade changes

**Steps**:
1. Clone GitLab repository
2. Create feature branch
3. For each cluster:
   - Locate Flux HelmRelease YAML
   - Update Istio version
4. Commit changes
5. Push branch
6. Create MR with:
   - Health report
   - Cluster list
   - Datadog dashboard links
   - Review checklist

**Output**: GitLab MR URL

**Human Gate**: User reviews and merges MR

### Phase 3: Post-Upgrade Validation

**Goal**: Verify upgrade success

**Steps**:
1. Wait for Flux sync
2. Monitor pod rollout
3. Soak period (60-120 minutes)
4. Query post-upgrade metrics
5. Compare with baseline
6. Check thresholds
7. Mark as validated or failed

**Output**: Validation report

### Phase 4: Failure Analysis (Optional)

**Goal**: Understand root cause of failure

**Steps**:
1. Collect failure data:
   - Validation results
   - Kubernetes events
   - Istio logs
   - Datadog graphs
2. Send to LLM for analysis
3. Receive structured report

**Output**: LLM analysis report

### Phase 5: Automated Rollback

**Goal**: Quickly revert failed upgrade

**Steps**:
1. Create rollback branch
2. Revert version changes
3. Create rollback MR
4. Send notifications
5. Wait for manual approval and merge

**Human Gate**: User reviews and merges rollback MR

## Data Flow

### Configuration Flow

```
config.yaml → GuardConfig → Components
            ↓
     AWS Secrets Manager → Credentials
```

### Cluster Metadata Flow

```
DynamoDB → ClusterRegistry → Cluster objects → Components
```

### Metrics Flow

```
Datadog API → Pre-check baseline → DynamoDB (state)
                                          ↓
                      Post-upgrade metrics → Comparison → Validation
```

### GitOps Flow

```
Local clone ← GitLab repo
     ↓
Update Flux configs
     ↓
Commit + Push → Feature branch
     ↓
Create MR → Human review → Merge
     ↓
Flux CD → Apply to cluster
```

## Design Decisions

### Why DynamoDB for State?

**Alternatives Considered**:
- Local file
- S3
- RDS

**Decision**: DynamoDB
- Serverless, no infrastructure
- Fast key-value access
- Built-in TTL for cleanup
- AWS-native integration

### Why GitOps via GitLab MRs?

**Alternatives Considered**:
- Direct kubectl apply
- Terraform/Pulumi
- FluxCD API

**Decision**: GitLab MRs
- Audit trail (all changes in Git)
- Human approval gate
- Existing GitOps workflow
- Rollback via Git revert

### Why Human Gates?

**Alternatives Considered**:
- Full automation
- Approval via API

**Decision**: Manual MR approval
- Safety for production
- Team awareness
- Accountability
- Emergency stop capability

### Why Datadog for Metrics?

**Alternatives Considered**:
- Prometheus/Grafana
- CloudWatch

**Decision**: Datadog
- Existing monitoring infrastructure
- Rich API
- Pre-built Istio dashboards
- APM integration

### Why Python?

**Alternatives Considered**:
- Go
- TypeScript

**Decision**: Python
- Rich ecosystem (boto3, kubernetes client)
- Fast development
- Easy testing with pytest
- Team familiarity

## Extension Points

### Custom Health Checks

Add custom checks by implementing:

```python
# src/guard/checks/custom_check.py
from guard.checks.base import HealthCheck

class CustomHealthCheck(HealthCheck):
    async def run(self, cluster: Cluster) -> HealthCheckResult:
        # Your custom logic
        pass
```

Register in configuration:

```yaml
custom_checks:
  - module: guard.checks.custom_check
    class: CustomHealthCheck
```

### Custom Metrics

Add custom Datadog queries:

```yaml
datadog:
  queries:
    custom_metric: "avg:custom.metric{cluster:{cluster_name}}"
```

### Custom Notifications

Implement notification handler:

```python
# src/guard/notifications/custom_notifier.py
from guard.notifications.base import Notifier

class CustomNotifier(Notifier):
    async def send(self, message: str, severity: str) -> None:
        # Your notification logic
        pass
```

### LLM Providers

Add custom LLM provider:

```python
# src/guard/llm/providers/custom.py
from guard.llm.base import LLMProvider

class CustomLLMProvider(LLMProvider):
    async def analyze(self, context: dict) -> str:
        # Your LLM integration
        pass
```

## Performance Considerations

### Parallel Execution

Currently, clusters in a batch are processed sequentially. Future enhancement will support parallel execution:

```yaml
execution:
  max_parallel_clusters: 5
```

### Rate Limiting

All external API calls are rate-limited:

```yaml
rate_limits:
  gitlab_api: 300   # requests per minute
  datadog_api: 300
  aws_api: 100
```

### Caching

Datadog queries are cached for 5 minutes to reduce API usage.

## Security Considerations

See [Security Documentation](security.md) for details.

**Key Points**:
- All credentials in AWS Secrets Manager
- IAM roles with least privilege
- Temporary credentials via STS AssumeRole
- Audit logging of all operations
- No credentials in code or config files

## Future Architecture Enhancements

### Multi-Region Coordination

Coordinate upgrades across regions:

```
Region 1 (Primary) → Region 2 → Region 3
```

### Blue/Green Control Plane

Deploy new Istio control plane alongside old:

```
Traffic split: 90% old / 10% new → 50/50 → 10/90 → 0/100
```

### Service Mesh Abstraction

Support multiple service meshes (Linkerd, Consul):

```python
class ServiceMeshProvider(ABC):
    @abstractmethod
    async def upgrade(self, version: str) -> None:
        pass
```

### Event-Driven Architecture

Use EventBridge for workflow orchestration:

```
Pre-checks complete → Event → Trigger GitOps
MR merged → Event → Trigger validation
```
