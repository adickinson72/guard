# Extensibility Guide

This document explains how GUARD (GitOps Upgrade Automation with Rollback Detection) can be extended and refactored to support GitOps upgrades for applications and services beyond Istio.

## Table of Contents

- [Overview](#overview)
- [Architecture for Extensibility](#architecture-for-extensibility)
- [Extending GUARD for Other Services](#extending-igu-for-other-services)
- [Application-Specific Validation](#application-specific-validation)
- [Immediate Extension Candidates](#immediate-extension-candidates)
- [Implementation Roadmap](#implementation-roadmap)
- [Example: Extending for Promtail/Loki](#example-extending-for-promtailloki)

## Overview

GUARD's core design is fundamentally service-agnostic. While it was originally built for Istio upgrades, the underlying architecture can be adapted to automate safe, progressive upgrades for any service that meets these criteria:

- **GitOps-managed**: Configuration stored in Git and deployed via GitOps tools (Flux, ArgoCD)
- **Kubernetes-native**: Runs on Kubernetes (EKS, GKE, AKS, etc.)
- **Observable**: Health and performance metrics available via kubectl and/or monitoring systems (Datadog, Prometheus, etc.)

### Core Principles That Enable Extensibility

1. **Generic Workflow**: Pre-checks → GitOps MR → Validation → Rollback
2. **Pluggable Validation**: Custom health checks can be added without modifying core logic
3. **Configuration-Driven**: Service-specific behavior defined in YAML config
4. **Abstract Interfaces**: Key components use abstract base classes

## Architecture for Extensibility

### Current Architecture (Istio-Specific)

```
┌─────────────────────────────────────────────────────────────┐
│  Pre-Check Engine                                           │
│  • Kubernetes health checks                                 │
│  • Istio-specific checks (istioctl analyze)                 │
│  • Datadog metrics (Istio-specific queries)                 │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  GitOps Manager                                             │
│  • Updates Flux HelmRelease for Istio                       │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  Validation Engine                                          │
│  • Post-upgrade Istio metrics                               │
│  • Istio-specific thresholds                                │
└─────────────────────────────────────────────────────────────┘
```

### Proposed Extensible Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Pre-Check Engine (Generic)                                 │
│  • Kubernetes health checks (generic)                       │
│  • Service health checks (pluggable)                        │
│  • Metrics baseline (pluggable)                             │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  GitOps Manager (Generic)                                   │
│  • Updates any Flux/ArgoCD resource                         │
│  • Configurable file patterns                               │
└─────────────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  Validation Engine (Generic)                                │
│  • Post-upgrade metrics (pluggable)                         │
│  • Service-specific thresholds (configurable)               │
└─────────────────────────────────────────────────────────────┘
```

### Key Abstraction: Service Provider Interface

The core abstraction is a `ServiceProvider` interface that encapsulates service-specific behavior:

```python
# src/igu/providers/base.py
from abc import ABC, abstractmethod
from typing import Any

class ServiceProvider(ABC):
    """Abstract base class for service-specific upgrade logic."""

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of the service (e.g., 'istio', 'promtail')."""
        pass

    @abstractmethod
    async def run_health_checks(
        self,
        cluster: Cluster,
        context: dict[str, Any]
    ) -> list[HealthCheckResult]:
        """Run service-specific health checks."""
        pass

    @abstractmethod
    async def get_baseline_metrics(
        self,
        cluster: Cluster,
        metrics_client: Any
    ) -> dict[str, float]:
        """Query baseline metrics for comparison."""
        pass

    @abstractmethod
    async def update_gitops_config(
        self,
        file_path: Path,
        target_version: str
    ) -> None:
        """Update GitOps configuration files."""
        pass

    @abstractmethod
    async def validate_upgrade(
        self,
        cluster: Cluster,
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
        thresholds: dict[str, float]
    ) -> ValidationResult:
        """Validate upgrade success."""
        pass

    @abstractmethod
    async def get_rollback_version(
        self,
        cluster: Cluster
    ) -> str:
        """Determine version to rollback to."""
        pass
```

## Extending GUARD for Other Services

### Step-by-Step Guide

#### 1. Create a Service Provider

Implement the `ServiceProvider` interface for your target service:

```python
# src/igu/providers/promtail.py
from igu.providers.base import ServiceProvider
from igu.core.models import Cluster, HealthCheckResult, ValidationResult

class PromtailProvider(ServiceProvider):
    """Service provider for Promtail/Loki upgrades."""

    @property
    def service_name(self) -> str:
        return "promtail"

    async def run_health_checks(
        self,
        cluster: Cluster,
        context: dict[str, Any]
    ) -> list[HealthCheckResult]:
        """Check Promtail DaemonSet and Loki connectivity."""
        results = []

        # Check DaemonSet status
        daemonset_healthy = await self._check_daemonset_health(cluster)
        results.append(daemonset_healthy)

        # Check Loki connectivity
        loki_reachable = await self._check_loki_connectivity(cluster)
        results.append(loki_reachable)

        return results

    async def get_baseline_metrics(
        self,
        cluster: Cluster,
        metrics_client: Any
    ) -> dict[str, float]:
        """Query Promtail-specific metrics."""
        queries = {
            "promtail_read_bytes_total": "rate(promtail_read_bytes_total[5m])",
            "promtail_encoded_bytes_total": "rate(promtail_encoded_bytes_total[5m])",
            "promtail_sent_bytes_total": "rate(promtail_sent_bytes_total[5m])",
            "loki_ingester_chunks_flushed_total": "rate(loki_ingester_chunks_flushed_total[5m])",
        }

        return await metrics_client.query_metrics(cluster, queries)

    async def update_gitops_config(
        self,
        file_path: Path,
        target_version: str
    ) -> None:
        """Update Promtail HelmRelease version."""
        # Load YAML
        # Update spec.chart.spec.version or image tag
        # Save YAML
        pass

    async def validate_upgrade(
        self,
        cluster: Cluster,
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
        thresholds: dict[str, float]
    ) -> ValidationResult:
        """Validate Promtail upgrade success."""
        violations = []

        # Check log ingestion rate hasn't dropped
        baseline_rate = baseline_metrics.get("promtail_sent_bytes_total", 0)
        current_rate = current_metrics.get("promtail_sent_bytes_total", 0)

        if current_rate < baseline_rate * 0.9:  # 10% drop threshold
            violations.append(
                f"Log ingestion rate dropped: {baseline_rate} -> {current_rate}"
            )

        return ValidationResult(
            cluster_id=cluster.cluster_id,
            passed=len(violations) == 0,
            metrics=current_metrics,
            threshold_violations=violations
        )

    async def get_rollback_version(
        self,
        cluster: Cluster
    ) -> str:
        """Get previous Promtail version from DynamoDB state."""
        # Query state table for last successful version
        pass
```

#### 2. Register the Provider

Add provider registration to configuration:

```yaml
# config.yaml
service_provider:
  type: promtail  # or 'istio', 'datadog-agent', etc.
  module: igu.providers.promtail
  class: PromtailProvider

# Service-specific configuration
promtail:
  daemonset_name: promtail
  namespace: logging
  loki_url: http://loki:3100
  validation_thresholds:
    log_ingestion_drop_percentage: 10
    error_rate_increase_percentage: 50
```

#### 3. Update Core Engine

Modify the core engine to use the service provider:

```python
# src/igu/core/engine.py
from igu.providers.base import ServiceProvider
from igu.providers.factory import ServiceProviderFactory

class UpgradeEngine:
    def __init__(self, config: IguConfig):
        self.config = config
        # Load service provider dynamically
        self.provider: ServiceProvider = ServiceProviderFactory.create(
            config.service_provider.type,
            config.service_provider.module,
            config.service_provider.class_name
        )

    async def run_pre_checks(self, clusters: list[Cluster]) -> dict[str, list[HealthCheckResult]]:
        results = {}
        for cluster in clusters:
            # Generic Kubernetes checks
            k8s_checks = await self._run_kubernetes_checks(cluster)

            # Service-specific checks (via provider)
            service_checks = await self.provider.run_health_checks(cluster, {})

            results[cluster.cluster_id] = k8s_checks + service_checks
        return results
```

## Application-Specific Validation

Different applications require different validation strategies. GUARD's extensibility model allows you to define custom validation logic per service.

### Common Validation Patterns

#### 1. Metrics-Based Validation

Most services can be validated by comparing metrics before and after upgrade:

```yaml
validation:
  type: metrics_comparison
  metrics:
    - name: error_rate
      query: "sum(rate(http_requests_total{status=~'5..'}[5m]))"
      threshold_increase_percentage: 50
    - name: latency_p95
      query: "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
      threshold_increase_percentage: 20
    - name: throughput
      query: "sum(rate(http_requests_total[5m]))"
      threshold_decrease_percentage: 10
```

#### 2. Health Endpoint Validation

For services with HTTP health endpoints:

```yaml
validation:
  type: health_endpoint
  endpoints:
    - url: http://service:8080/health
      expected_status: 200
      timeout_seconds: 10
    - url: http://service:8080/ready
      expected_status: 200
      timeout_seconds: 10
```

#### 3. Custom kubectl Checks

For Kubernetes-native validations:

```yaml
validation:
  type: kubectl
  checks:
    - name: daemonset_ready
      command: kubectl get daemonset -n logging promtail -o jsonpath='{.status.numberReady}'
      expected_value: "{.status.desiredNumberScheduled}"
    - name: no_crashloops
      command: kubectl get pods -n logging -l app=promtail -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'
      max_value: 5
```

#### 4. Log-Based Validation

Check for error patterns in logs:

```yaml
validation:
  type: log_analysis
  queries:
    - source: datadog
      query: 'service:promtail status:error'
      max_count_increase: 100
    - source: kubectl
      command: kubectl logs -n logging -l app=promtail --since=10m
      error_patterns:
        - "panic:"
        - "fatal error"
        - "connection refused"
      max_occurrences: 5
```

## Immediate Extension Candidates

Based on the issue requirements, here are the immediate candidates for extending GUARD:

### 1. Promtail/Loki

**Use Case**: Centralized logging infrastructure upgrades

**Validation Requirements**:
- DaemonSet health (all nodes have Promtail pods)
- Loki connectivity
- Log ingestion rate (bytes/sec)
- Log parsing errors
- Loki ingester health

**GitOps Config**: Flux HelmRelease for Promtail and Loki

**Implementation Complexity**: Low
- Simple DaemonSet model
- Prometheus metrics available
- Similar to Istio pattern

**Example Provider**: See [Example: Extending for Promtail/Loki](#example-extending-for-promtailloki) below

### 2. Datadog Agent

**Use Case**: Monitoring agent upgrades across all clusters

**Validation Requirements**:
- DaemonSet health
- Metrics submission rate to Datadog
- Agent health checks (via Datadog API)
- No increase in agent errors
- All integrations still reporting

**GitOps Config**: Flux HelmRelease for Datadog Agent

**Implementation Complexity**: Low-Medium
- DaemonSet model
- Can validate via Datadog API
- May need Datadog-specific SDK integration

**Unique Considerations**:
- Agent upgrade affects monitoring itself (GUARD uses Datadog)
- Need fallback validation (kubectl-based)
- Careful coordination to avoid blind spots

### 3. Cert-Manager

**Use Case**: Certificate management infrastructure

**Validation Requirements**:
- Deployment health
- Certificate issuance working
- No expired certificates
- Webhook availability

**GitOps Config**: Flux HelmRelease for cert-manager

**Implementation Complexity**: Medium
- More complex validation (certificate lifecycle)
- Need to test actual certificate issuance
- CRD upgrades may require special handling

### 4. External DNS

**Use Case**: DNS management automation

**Validation Requirements**:
- Deployment health
- DNS records being created/updated
- No stale DNS entries
- Provider API connectivity (Route53, CloudFlare, etc.)

**GitOps Config**: Flux HelmRelease

**Implementation Complexity**: Medium
- Need DNS provider API integration
- Validation requires checking actual DNS records
- Different providers have different APIs

### 5. NGINX Ingress Controller

**Use Case**: Ingress traffic management

**Validation Requirements**:
- DaemonSet/Deployment health
- Ingress rules applied
- Traffic throughput maintained
- Latency within thresholds
- No 5xx error rate increase

**GitOps Config**: Flux HelmRelease

**Implementation Complexity**: Low-Medium
- Metrics readily available
- Similar to Istio (traffic management)
- May need to test actual ingress routes

## Implementation Roadmap

### Phase 1: Core Refactoring (2-3 weeks)

**Goal**: Make existing code service-agnostic

Tasks:
1. Create `ServiceProvider` abstract base class
2. Extract Istio-specific logic into `IstioProvider`
3. Refactor `PreCheckEngine` to use provider pattern
4. Refactor `ValidationEngine` to use provider pattern
5. Update configuration schema to support multiple providers
6. Add provider factory for dynamic loading
7. Update tests to work with provider abstraction

**Deliverables**:
- `src/igu/providers/base.py` - Abstract interface
- `src/igu/providers/istio.py` - Istio implementation
- `src/igu/providers/factory.py` - Provider factory
- Updated configuration schema
- Comprehensive tests

### Phase 2: Promtail/Loki Extension (1-2 weeks)

**Goal**: Prove extensibility with first non-Istio service

Tasks:
1. Implement `PromtailProvider`
2. Define Promtail-specific validation logic
3. Create configuration templates
4. Add integration tests
5. Document usage

**Deliverables**:
- `src/igu/providers/promtail.py`
- `examples/promtail-config.yaml`
- `docs/providers/promtail.md`
- Integration tests
- Migration guide

### Phase 3: Datadog Agent Extension (1-2 weeks)

**Goal**: Second extension to validate pattern

Tasks:
1. Implement `DatadogAgentProvider`
2. Handle self-monitoring challenge (agent affects metrics)
3. Implement kubectl-based fallback validation
4. Add Datadog API health checks
5. Document special considerations

**Deliverables**:
- `src/igu/providers/datadog_agent.py`
- `examples/datadog-agent-config.yaml`
- `docs/providers/datadog-agent.md`
- Tests and documentation

### Phase 4: Additional Tooling (2-3 weeks)

**Goal**: Build common utilities for all providers

Tasks:
1. Generic kubectl validation framework
2. Generic metrics comparison utilities
3. Log analysis utilities
4. DNS validation utilities (for External DNS)
5. Certificate validation utilities (for cert-manager)
6. Health endpoint checker
7. Common test fixtures

**Deliverables**:
- `src/igu/validation/kubectl_validator.py`
- `src/igu/validation/metrics_comparator.py` (enhanced)
- `src/igu/validation/log_analyzer.py`
- `src/igu/validation/dns_validator.py`
- `src/igu/validation/cert_validator.py`
- `src/igu/validation/http_health_checker.py`

### Phase 5: Documentation & Examples (1 week)

**Goal**: Complete documentation for extensibility

Tasks:
1. Write comprehensive extensibility guide (this document)
2. Create provider implementation tutorial
3. Document validation patterns
4. Provide real-world examples
5. Create migration guide for Istio users
6. Video walkthrough (optional)

**Deliverables**:
- `docs/extensibility.md` (this document)
- `docs/tutorials/creating-a-provider.md`
- `docs/validation-patterns.md`
- `docs/migration-from-istio-only.md`
- Example implementations in `examples/providers/`

### Phase 6: Multi-Service Support (Future)

**Goal**: Support upgrading multiple services in coordinated fashion

Tasks:
1. Multi-service batch configuration
2. Dependency management (upgrade A before B)
3. Cross-service validation
4. Coordinated rollback

**Deliverables**:
- Multi-service upgrade orchestration
- Enhanced configuration schema
- Dependency graph resolver

## Example: Extending for Promtail/Loki

Here's a complete example of extending GUARD for Promtail/Loki upgrades.

### 1. Provider Implementation

```python
# src/igu/providers/promtail.py
from pathlib import Path
from typing import Any
import yaml
from igu.providers.base import ServiceProvider
from igu.core.models import Cluster, HealthCheckResult, ValidationResult, CheckStatus
from igu.clients.kubernetes import KubernetesClient

class PromtailProvider(ServiceProvider):
    """Service provider for Promtail/Loki log aggregation upgrades."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.daemonset_name = config.get("daemonset_name", "promtail")
        self.namespace = config.get("namespace", "logging")
        self.loki_url = config.get("loki_url", "http://loki:3100")

    @property
    def service_name(self) -> str:
        return "promtail"

    async def run_health_checks(
        self,
        cluster: Cluster,
        context: dict[str, Any]
    ) -> list[HealthCheckResult]:
        """Run Promtail-specific health checks."""
        results = []
        k8s_client = context.get("k8s_client")

        # Check 1: DaemonSet status
        daemonset_status = await k8s_client.get_daemonset_status(
            self.namespace,
            self.daemonset_name
        )

        desired = daemonset_status.get("desired_number_scheduled", 0)
        ready = daemonset_status.get("number_ready", 0)

        results.append(HealthCheckResult(
            cluster_id=cluster.cluster_id,
            check_name="promtail_daemonset_health",
            status=CheckStatus.PASS if ready == desired else CheckStatus.FAIL,
            message=f"Promtail pods ready: {ready}/{desired}",
            timestamp=datetime.utcnow(),
            details=daemonset_status
        ))

        # Check 2: Loki connectivity from Promtail pods
        loki_check = await self._check_loki_connectivity(cluster, k8s_client)
        results.append(loki_check)

        # Check 3: Recent log ingestion
        ingestion_check = await self._check_log_ingestion(cluster, context)
        results.append(ingestion_check)

        return results

    async def _check_loki_connectivity(
        self,
        cluster: Cluster,
        k8s_client: KubernetesClient
    ) -> HealthCheckResult:
        """Verify Promtail can reach Loki."""
        # Execute curl to Loki /ready endpoint from a Promtail pod
        pods = await k8s_client.get_pods(
            self.namespace,
            label_selector=f"app={self.daemonset_name}"
        )

        if not pods:
            return HealthCheckResult(
                cluster_id=cluster.cluster_id,
                check_name="loki_connectivity",
                status=CheckStatus.FAIL,
                message="No Promtail pods found",
                timestamp=datetime.utcnow(),
                details={}
            )

        # Test from first pod
        test_pod = pods[0]
        result = await k8s_client.exec_in_pod(
            self.namespace,
            test_pod["name"],
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{self.loki_url}/ready"]
        )

        status = CheckStatus.PASS if result.get("stdout", "").strip() == "200" else CheckStatus.FAIL

        return HealthCheckResult(
            cluster_id=cluster.cluster_id,
            check_name="loki_connectivity",
            status=status,
            message=f"Loki reachable from Promtail: HTTP {result.get('stdout', 'unknown')}",
            timestamp=datetime.utcnow(),
            details=result
        )

    async def _check_log_ingestion(
        self,
        cluster: Cluster,
        context: dict[str, Any]
    ) -> HealthCheckResult:
        """Check that logs are being ingested recently."""
        metrics_client = context.get("metrics_client")

        # Query Promtail metrics
        query = f'rate(promtail_sent_bytes_total{{cluster="{cluster.cluster_id}"}}[5m])'
        result = await metrics_client.query(query)

        bytes_per_sec = result.get("value", 0)
        status = CheckStatus.PASS if bytes_per_sec > 0 else CheckStatus.WARN

        return HealthCheckResult(
            cluster_id=cluster.cluster_id,
            check_name="log_ingestion_active",
            status=status,
            message=f"Log ingestion rate: {bytes_per_sec} bytes/sec",
            timestamp=datetime.utcnow(),
            details={"bytes_per_second": bytes_per_sec}
        )

    async def get_baseline_metrics(
        self,
        cluster: Cluster,
        metrics_client: Any
    ) -> dict[str, float]:
        """Query baseline metrics for Promtail/Loki."""
        queries = {
            "promtail_sent_bytes_rate": f'rate(promtail_sent_bytes_total{{cluster="{cluster.cluster_id}"}}[5m])',
            "promtail_encoded_bytes_rate": f'rate(promtail_encoded_bytes_total{{cluster="{cluster.cluster_id}"}}[5m])',
            "promtail_dropped_entries_rate": f'rate(promtail_dropped_entries_total{{cluster="{cluster.cluster_id}"}}[5m])',
            "loki_ingester_chunks_flushed_rate": f'rate(loki_ingester_chunks_flushed_total{{cluster="{cluster.cluster_id}"}}[5m])',
        }

        metrics = {}
        for metric_name, query in queries.items():
            result = await metrics_client.query(query)
            metrics[metric_name] = result.get("value", 0.0)

        return metrics

    async def update_gitops_config(
        self,
        file_path: Path,
        target_version: str
    ) -> None:
        """Update Promtail HelmRelease version in Flux config."""
        with open(file_path, 'r') as f:
            config = yaml.safe_load(f)

        # Update chart version
        if 'spec' in config and 'chart' in config['spec']:
            config['spec']['chart']['spec']['version'] = target_version

        with open(file_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

    async def validate_upgrade(
        self,
        cluster: Cluster,
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
        thresholds: dict[str, float]
    ) -> ValidationResult:
        """Validate Promtail upgrade success."""
        violations = []

        # Check log ingestion rate hasn't dropped significantly
        baseline_rate = baseline_metrics.get("promtail_sent_bytes_rate", 0)
        current_rate = current_metrics.get("promtail_sent_bytes_rate", 0)
        max_drop = thresholds.get("log_ingestion_drop_percentage", 10)

        if baseline_rate > 0:
            drop_percentage = ((baseline_rate - current_rate) / baseline_rate) * 100
            if drop_percentage > max_drop:
                violations.append(
                    f"Log ingestion dropped {drop_percentage:.1f}% "
                    f"(threshold: {max_drop}%): {baseline_rate:.0f} -> {current_rate:.0f} bytes/sec"
                )

        # Check dropped entries haven't increased significantly
        baseline_drops = baseline_metrics.get("promtail_dropped_entries_rate", 0)
        current_drops = current_metrics.get("promtail_dropped_entries_rate", 0)
        max_increase = thresholds.get("dropped_entries_increase_percentage", 100)

        if baseline_drops > 0:
            increase_percentage = ((current_drops - baseline_drops) / baseline_drops) * 100
            if increase_percentage > max_increase:
                violations.append(
                    f"Dropped log entries increased {increase_percentage:.1f}% "
                    f"(threshold: {max_increase}%): {baseline_drops:.2f} -> {current_drops:.2f} entries/sec"
                )

        return ValidationResult(
            cluster_id=cluster.cluster_id,
            passed=len(violations) == 0,
            metrics=current_metrics,
            threshold_violations=violations
        )

    async def get_rollback_version(
        self,
        cluster: Cluster
    ) -> str:
        """Get previous Promtail version for rollback."""
        # Implementation would query state store for last successful version
        # For now, return placeholder
        return cluster.get("previous_promtail_version", "6.15.0")
```

### 2. Configuration

```yaml
# ~/.guard/promtail-config.yaml

# Service provider configuration
service_provider:
  type: promtail
  module: igu.providers.promtail
  class: PromtailProvider

# Promtail-specific settings
promtail:
  daemonset_name: promtail
  namespace: logging
  loki_url: http://loki.logging.svc.cluster.local:3100

  # Validation thresholds
  validation_thresholds:
    log_ingestion_drop_percentage: 10  # Allow up to 10% drop
    dropped_entries_increase_percentage: 100  # Allow 2x increase in drops
    soak_period_minutes: 30

# Datadog configuration (for metrics)
datadog:
  api_key_secret: igu/datadog-credentials
  app_key_secret: igu/datadog-credentials

# GitLab configuration
gitlab:
  url: https://gitlab.company.com
  token_secret: igu/gitlab-token
  project_id: 12345

# Cluster registry
registry:
  dynamodb_table: igu-clusters
  region: us-east-1

# Batch definitions
batches:
  test:
    - cluster-test-1
  dev-wave-1:
    - cluster-dev-1
    - cluster-dev-2
  prod-wave-1:
    - cluster-prod-1
    - cluster-prod-2
```

### 3. Usage

```bash
# Validate configuration
igu validate --config ~/.guard/promtail-config.yaml

# List clusters in batch
igu list --batch prod-wave-1 --config ~/.guard/promtail-config.yaml

# Run pre-checks and create upgrade MR
igu run \
  --batch prod-wave-1 \
  --target-version 6.16.0 \
  --config ~/.guard/promtail-config.yaml

# After MR is merged, monitor and validate
igu monitor \
  --batch prod-wave-1 \
  --soak-period 30 \
  --config ~/.guard/promtail-config.yaml

# Rollback if needed
igu rollback \
  --batch prod-wave-1 \
  --config ~/.guard/promtail-config.yaml
```

### 4. Cluster Registry Updates

Add Promtail-specific metadata to cluster registry:

```python
# Example DynamoDB item for Promtail
{
    "cluster_id": "cluster-prod-1",
    "batch_id": "prod-wave-1",
    "environment": "production",
    "region": "us-east-1",
    "aws_role_arn": "arn:aws:iam::123456789:role/GUARDRole",
    "gitlab_repo": "infrastructure/k8s-configs",
    "flux_config_path": "clusters/prod-1/logging/promtail-helmrelease.yaml",
    "current_promtail_version": "6.15.0",
    "previous_promtail_version": "6.14.0",
    "service_type": "promtail",  # New field
    "datadog_tags": {
        "cluster": "cluster-prod-1",
        "env": "production",
        "service": "promtail"
    }
}
```

## Conclusion

GUARD's architecture is fundamentally extensible. By abstracting service-specific logic into pluggable providers and making validation configurable, GUARD can be adapted to automate safe upgrades for any Kubernetes-native service that can be validated via kubectl and monitoring metrics.

The roadmap outlines a clear path from the current Istio-specific implementation to a general-purpose GitOps upgrade automation tool. Starting with Promtail/Loki and Datadog Agent as the first extension targets provides a pragmatic approach to proving the extensibility pattern while delivering immediate value.

As GUARD evolves into a multi-service upgrade platform, the core principles remain:
- **Safety first** with comprehensive pre-checks
- **GitOps-native** with human approval gates
- **Observable** with rich metrics and logging
- **Resumable** with persistent state management

These principles, combined with the extensible architecture, position GUARD as a foundational platform for automating infrastructure upgrades at scale.
