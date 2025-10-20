# Black Box Design in GUARD

## Overview

GUARD follows **black box design principles** where each module is replaceable without breaking the system. This document explains the architecture and principles.

## Core Philosophy

> "It's faster to write five lines of code today than to write one line today and edit it in the future."

Every module in GUARD is designed to be:
- **Understandable** by any developer
- **Replaceable** without knowing internal implementation
- **Testable** in isolation
- **Maintainable** over years

## Architecture Layers

```
┌──────────────────────────────────────────────────────────┐
│  CLI Layer (Click commands)                              │
└──────────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────┐
│  Orchestrators (Generic Coordination)                    │
│  - CheckOrchestrator                                     │
│  - ValidationOrchestrator                                │
│  - GitOpsOrchestrator                                    │
└──────────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────┐
│  Interfaces (Abstract Contracts)                         │
│  - CloudProvider, KubernetesProvider                     │
│  - MetricsProvider, GitOpsProvider                       │
│  - Check, Validator, ConfigUpdater                       │
└──────────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────┐
│  Adapters (External Service Wrappers)                    │
│  - AWSAdapter, KubernetesAdapter                         │
│  - DatadogAdapter, GitLabAdapter                         │
│  - DynamoDBAdapter                                       │
└──────────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────────┐
│  Service Modules (Service-Specific Logic)                │
│  - services/istio/ (all Istio code)                      │
│  - Future: services/promtail/, services/datadog-agent/   │
└──────────────────────────────────────────────────────────┘
```

## Black Box Principles Applied

### 1. Interfaces Define "WHAT", Not "HOW"

**Good Interface**:
```python
class MetricsProvider(ABC):
    async def query_scalar(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """Query a single scalar value."""
```

**Bad Interface** (leaks implementation):
```python
class DatadogClient:
    def query_datadog_api(self, dd_query: str):
        """Leaks Datadog-specific details!"""
```

### 2. Adapters Hide External Dependencies

No direct `import boto3` or `import datadog_api_client` in business logic!

All external libraries are wrapped in adapters that implement clean interfaces.

### 3. Service Modules Contain All Service-Specific Code

All Istio-specific code lives in `src/igu/services/istio/`:
- Checks: `services/istio/checks/`
- Validators: `services/istio/validators/`
- Config updater: `gitops/updaters/istio_helm_updater.py`

When adding Promtail support:
- Create `services/promtail/` with same structure
- Core orchestrators unchanged

### 4. Registries Enable Pluggability

```python
# Register Istio-specific components
istio_service = IstioService()
istio_service.register_checks(check_registry)
istio_service.register_validators(validator_registry)

# Orchestrators use registered components
orchestrator.run_checks(cluster, context)  # Runs all registered checks
```

## Module Boundaries

### CloudProvider
**What**: Assume IAM roles, get secrets, get cluster info
**How**: Hidden (boto3, STS, Secrets Manager)
**Replace**: Swap AWSAdapter for GCPAdapter without changing callers

### KubernetesProvider
**What**: Get nodes/pods, check readiness, restart workloads
**How**: Hidden (kubernetes Python client)
**Replace**: Could use kubectl subprocess instead

### MetricsProvider
**What**: Query timeseries, check alerts
**How**: Hidden (Datadog API)
**Replace**: Swap DatadogAdapter for PrometheusAdapter

### GitOpsProvider
**What**: Create branches, update files, create MRs
**How**: Hidden (python-gitlab)
**Replace**: Swap GitLabAdapter for GitHubAdapter

## Benefits

1. **Easy Testing**: Mock interfaces, not concrete implementations
2. **Technology Changes**: Swap Datadog for Prometheus without touching business logic
3. **Service Addition**: Add Promtail by creating `services/promtail/` - core unchanged
4. **Team Autonomy**: Teams can own specific adapters/services independently
5. **Debugging**: Clear boundaries make issues easier to isolate

## Path to ServiceProvider Pattern

Current architecture sets foundation for full ServiceProvider pattern:

```python
# Future: Multi-service support
class ServiceProvider(ABC):
    def register_checks(self, registry: CheckRegistry): ...
    def register_validators(self, registry: ValidatorRegistry): ...
    def get_config_updater(self) -> ConfigUpdater: ...

# services/istio/ becomes providers/istio.py
class IstioProvider(ServiceProvider):
    ...

# services/promtail/ becomes providers/promtail.py
class PromtailProvider(ServiceProvider):
    ...
```

## Rules for Maintainers

1. **Never import external libs in orchestrators** - use interfaces
2. **New service? Create services/{name}/** - don't modify core
3. **New external dependency? Create adapter** - don't use directly
4. **Can't understand a module? It should be replaceable** - that's the point
5. **Breaking change? Module interface must stay stable** - implementation can change

## Examples

### Adding Prometheus Support

1. Create `PrometheusAdapter` implementing `MetricsProvider`
2. Update config to use `PrometheusAdapter` instead of `DatadogAdapter`
3. No changes to orchestrators or business logic

### Adding GitHub Support

1. Create `GitHubAdapter` implementing `GitOpsProvider`
2. Update config
3. GitOpsOrchestrator works unchanged

### Adding Promtail Service

1. Create `services/promtail/` directory
2. Implement promtail checks, validators, config updater
3. Create `PromtailService` facade
4. Register components at startup
5. Core orchestrators work unchanged

## Success Metrics

- Can swap adapters without touching orchestrators ✅
- Can add new service without modifying core ✅
- New developer can understand any module in < 1 hour ✅
- Tests use mocked interfaces, not real services ✅
- All Istio code isolated in services/istio/ ✅
