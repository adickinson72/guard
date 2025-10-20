<div align="center">

```
  ________ ____ ___  _____ __________________
 /  _____/|    |   \/  _  \\______   \______ \
/   \  ___|    |   /  /_\  \|       _/|    |  \
\    \_\  \    |  /    |    \    |   \|    `   \
 \______  /______/\____|__  /____|_  /_______  /
        \/                \/       \/        \/
```

# GitOps Upgrade Automation with Rollback Detection

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://pytest.org/)

**Automate safe, progressive Istio upgrades across multiple EKS clusters using GitOps workflows**

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#documentation) • [Contributing](#contributing)

</div>

---

## Overview

Managing Istio upgrades across 75+ EKS clusters is complex and risky. GUARD automates the entire upgrade lifecycle with:

- 🔍 **Automated pre-upgrade health checks** using Datadog metrics and Kubernetes state
- 🔀 **GitLab MR creation** with automated configuration updates
- 📊 **Progressive rollout strategy** (test → dev → staging → prod batches)
- ✅ **Post-upgrade validation** with automated rollback on failure
- 🤖 **Optional LLM-powered analysis** for failure investigation
- 🛡️ **Human-in-the-loop gates** for safety-critical operations

### Why GUARD?

**Before GUARD:**
- ❌ Manual, error-prone upgrade procedures
- ❌ Inconsistent validation across clusters
- ❌ Risk of production outages
- ❌ Days/weeks to upgrade all clusters

**After GUARD:**
- ✅ Automated, repeatable upgrade workflow
- ✅ Consistent health validation with Datadog
- ✅ Automatic rollback on failure
- ✅ Hours to upgrade all clusters safely

---

## Features

### Core Workflow
- **Stateful Execution**: Resumable workflow with state tracking in DynamoDB
- **Batch Management**: Upgrade clusters in controlled waves (test → dev → staging → prod)
- **Pre-Flight Checks**: Validate cluster health before upgrade
  - Kubernetes control plane status
  - Istio pod health and configuration (`istioctl analyze`)
  - Datadog metrics baseline
  - Active alert detection
- **GitOps Integration**: Creates GitLab MRs with automated Flux config updates
- **Pod Restart**: Automatically restarts pods with sidecars after control plane upgrade
  - Queries namespaces with `istio-injection=enabled`
  - Rolling restart of Deployments, StatefulSets, and DaemonSets
  - Ensures sidecar proxy versions match new control plane
- **Post-Upgrade Validation**: Comprehensive health checks with configurable soak period
- **Automated Rollback**: Creates rollback MR on validation failure

### Safety Features
- **Human Gates**: Manual approval required for GitLab MRs
- **Fail-Fast**: Halts batch upgrade if any cluster fails pre-checks
- **Rollback Protection**: Requires manual approval for rollback MRs
- **Audit Logging**: Comprehensive structured logging for all operations

### Observability
- **Datadog Integration**: Query metrics, check alerts, validate SLOs
- **Self-Monitoring**: GUARD emits metrics about its own operations
- **LLM Analysis** *(optional)*: AI-powered failure root cause analysis

---

## Quick Start

### Prerequisites

- Python 3.11+
- AWS credentials with appropriate IAM roles
- Access to EKS clusters (via IAM roles)
- GitLab personal access token
- Datadog API and App keys
- `kubectl` and `istioctl` installed

### Installation Options

#### Option 1: Local CLI Installation

```bash
# Install GUARD
pip install igu

# Or install from source
git clone https://github.com/your-org/igu.git
cd igu
pip install -e .
```

#### Option 2: Kubernetes Deployment (Recommended for Production)

For production environments, run GUARD inside an EKS pod to leverage Pod Identity for cross-account access:

```bash
# Build and push Docker image
docker build -t <YOUR_REGISTRY>/igu:latest .
docker push <YOUR_REGISTRY>/igu:latest

# Deploy to Kubernetes
kubectl apply -k k8s/

# Execute upgrades
kubectl exec -n igu-system deploy/igu -- igu run --batch prod-wave-1 --target-version 1.20.0
```

See [Kubernetes Deployment Guide](docs/kubernetes-deployment.md) for complete instructions.

### Configuration

1. Create DynamoDB table:

```bash
./scripts/setup-dynamodb.sh
```

2. Store credentials in AWS Secrets Manager:

```bash
# GitLab token
aws secretsmanager create-secret \
    --name igu/gitlab-token \
    --secret-string "glpat-xxxxxxxxxxxx"

# Datadog credentials
aws secretsmanager create-secret \
    --name igu/datadog-credentials \
    --secret-string '{"api_key":"xxx","app_key":"xxx"}'
```

3. Create configuration file:

```bash
mkdir -p ~/.guard
cp examples/config.yaml.example ~/.guard/config.yaml
# Edit ~/.guard/config.yaml with your settings
```

4. Populate cluster registry (see [Configuration Guide](docs/configuration.md))

### Basic Usage

```bash
# Validate configuration
igu validate --config ~/.guard/config.yaml

# List clusters and their status
igu list --batch prod-wave-1

# Run pre-checks and create upgrade MR
igu run --batch prod-wave-1 --target-version 1.20.0

# After MR is merged, monitor upgrade and validate
igu monitor --batch prod-wave-1 --soak-period 60

# If needed, trigger manual rollback
igu rollback --batch prod-wave-1
```

### Complete Upgrade Workflow

```bash
# 1. Test cluster first
igu run --batch test --target-version 1.20.0
# → Review and merge MR in GitLab
igu monitor --batch test

# 2. Development clusters (wave 1)
igu run --batch dev-wave-1 --target-version 1.20.0
# → Review and merge MR
igu monitor --batch dev-wave-1

# 3. Development clusters (wave 2)
igu run --batch dev-wave-2 --target-version 1.20.0
# → Review and merge MR
igu monitor --batch dev-wave-2

# 4. Staging clusters
igu run --batch staging --target-version 1.20.0
# → Review and merge MR
igu monitor --batch staging --soak-period 120  # Extended soak

# 5. Production (critical services)
igu run --batch prod-wave-1 --target-version 1.20.0
# → Review and merge MR (notify on-call team)
igu monitor --batch prod-wave-1 --soak-period 120

# 6. Production (remaining)
igu run --batch prod-wave-2 --target-version 1.20.0
# → Review and merge MR
igu monitor --batch prod-wave-2
```

---

## Architecture

### High-Level Design

```
┌─────────────┐
│  GUARD CLI    │  ← User interaction
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────┐
│  Core Engine Layer                              │
│  • Pre-Check Engine                             │
│  • Validation Engine                            │
│  • Rollback Engine                              │
│  • GitOps Manager                               │
│  • State Manager (DynamoDB)                     │
└──────┬──────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────┐
│  Integration Layer                              │
│  • AWS Client (STS, EKS, Secrets Manager)       │
│  • Kubernetes Client                            │
│  • Datadog Client (Metrics, Monitors)           │
│  • GitLab Client (MRs, Branches)                │
│  • Istioctl Wrapper                             │
└─────────────────────────────────────────────────┘
```

### Workflow Phases

1. **Phase 0**: Setup (DynamoDB, IAM, Secrets)
2. **Phase 1**: Pre-Upgrade Checks (K8s, Istio, Datadog)
3. **Phase 2**: GitOps Change (Create MR, Update Flux config)
4. **Phase 3**: Post-Upgrade Validation (Soak, Compare metrics)
5. **Phase 4**: Failure Analysis *(optional LLM)*
6. **Phase 5**: Automated Rollback (Create rollback MR)

See [Architecture Documentation](docs/architecture.md) for details.

---

## Testing

GUARD is built with **Test-Driven Development (TDD)** principles:

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=igu --cov-report=html

# Run specific test types
pytest tests/unit/           # Unit tests only
pytest tests/integration/    # Integration tests
pytest tests/e2e/            # End-to-end tests

# Run with markers
pytest -m "not slow"         # Skip slow tests
pytest -m "requires_aws"     # AWS integration tests only
```

### Test Structure

```
tests/
├── unit/                    # Fast, isolated unit tests
│   ├── test_cluster_registry.py
│   ├── test_pre_checks.py
│   ├── test_gitops.py
│   └── ...
├── integration/             # Integration with external services
│   ├── test_aws_integration.py
│   ├── test_datadog_integration.py
│   ├── test_gitlab_integration.py
│   └── ...
├── e2e/                     # Full workflow tests
│   └── test_full_workflow.py
└── conftest.py              # Shared fixtures
```

### Test Coverage Goals

- **Unit Tests**: 90%+ coverage
- **Integration Tests**: All external service interactions
- **E2E Tests**: Complete upgrade workflow simulation

### Writing Tests

We follow TDD practices:

1. **Write the test first** (red)
2. **Write minimal code** to pass (green)
3. **Refactor** while keeping tests passing (refactor)

Example:

```python
# tests/unit/test_cluster_registry.py
import pytest
from igu.registry.cluster_registry import ClusterRegistry

def test_get_clusters_by_batch_returns_correct_clusters(mock_dynamodb):
    """Test that clusters are correctly filtered by batch_id."""
    registry = ClusterRegistry(table_name="test-table")

    # Arrange: Setup test data
    test_clusters = [
        {"cluster_id": "cluster-1", "batch_id": "prod-wave-1"},
        {"cluster_id": "cluster-2", "batch_id": "prod-wave-1"},
        {"cluster_id": "cluster-3", "batch_id": "dev-wave-1"},
    ]
    # ... mock DynamoDB responses

    # Act: Call the method
    result = registry.get_clusters_by_batch("prod-wave-1")

    # Assert: Verify results
    assert len(result) == 2
    assert result[0].cluster_id == "cluster-1"
    assert result[1].cluster_id == "cluster-2"
```

See [Testing Guide](docs/testing.md) for detailed testing practices.

---

## Documentation

- **[Getting Started](docs/getting-started.md)**: Installation and first upgrade
- **[Kubernetes Deployment](docs/kubernetes-deployment.md)**: Running GUARD in EKS with Pod Identity
- **[Architecture](docs/architecture.md)**: System design and components
- **[Extensibility Guide](docs/extensibility.md)**: Extending GUARD for other services beyond Istio
- **[Configuration](docs/configuration.md)**: Configuration reference
- **[Testing Guide](docs/testing.md)**: Writing and running tests
- **[Contributing](docs/contributing.md)**: Development guidelines
- **[API Reference](docs/api-reference.md)**: Python API documentation

### Examples

- **[Basic Usage](docs/examples/basic-usage.md)**: Simple upgrade scenarios
- **[Advanced Scenarios](docs/examples/advanced-scenarios.md)**: Complex multi-region upgrades
- **[Troubleshooting](docs/examples/troubleshooting.md)**: Common issues and solutions

---

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/your-org/igu.git
cd igu

# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Install pre-commit hooks
poetry run pre-commit install

# Run tests
poetry run pytest

# Run linting
poetry run ruff check .
poetry run mypy src/
```

### Project Structure

```
igu/
├── src/igu/                 # Source code
│   ├── cli/                 # CLI commands
│   ├── core/                # Core models and config
│   ├── registry/            # Cluster registry
│   ├── checks/              # Health checks
│   ├── validation/          # Post-upgrade validation
│   ├── gitops/              # GitLab operations
│   ├── rollback/            # Rollback automation
│   ├── clients/             # External service clients
│   └── utils/               # Utilities
├── tests/                   # Test suite
├── docs/                    # Documentation
├── scripts/                 # Setup scripts
└── examples/                # Configuration examples
```

### Code Quality

We maintain high code quality standards:

- **Linting**: `ruff` for fast Python linting
- **Type Checking**: `mypy` for static type analysis
- **Testing**: `pytest` with 90%+ coverage requirement
- **Formatting**: `ruff format` (Black-compatible)
- **Pre-commit Hooks**: Automated checks before commit

---

## Security

### Credential Management

- ✅ Store credentials in AWS Secrets Manager or HashiCorp Vault
- ✅ Use IAM roles with least-privilege access
- ✅ Rotate credentials regularly
- ✅ Use temporary credentials via AWS STS AssumeRole
- ❌ Never commit credentials to Git
- ❌ Never store credentials in config files

### IAM Permissions

See [Security Documentation](docs/security.md) for required IAM policies.

### Audit Logging

All operations are logged with structured JSON including:
- User/role executing command
- Batch/clusters affected
- Pre-check and validation results
- MR URLs and outcomes

---

## Roadmap

### Phase 1: MVP (Current)
- [x] Core workflow (run → monitor → rollback)
- [x] DynamoDB state management
- [x] Datadog health checks
- [x] GitLab MR automation
- [x] Basic CLI

### Phase 2: Extensibility & Multi-Service Support
- [ ] **Core Refactoring**: Extract Istio-specific logic into pluggable service providers
- [ ] **Promtail/Loki Support**: First extension target for log aggregation upgrades
- [ ] **Datadog Agent Support**: Monitoring agent upgrade automation
- [ ] **Generic Validation Framework**: Reusable validation utilities for kubectl, metrics, logs
- [ ] **Provider Documentation**: Comprehensive guide for implementing custom providers

See [Extensibility Guide](docs/extensibility.md) for detailed implementation plan.

**Why Extensibility?** GUARD's core workflow (pre-checks → GitOps → validation → rollback) is service-agnostic. By refactoring into a provider-based architecture, GUARD can automate safe upgrades for any Kubernetes-native service validated via kubectl and monitoring metrics.

**Immediate Candidates**:
- Promtail/Loki (centralized logging)
- Datadog Agent (monitoring infrastructure)
- Cert-Manager (certificate management)
- External DNS (DNS automation)
- NGINX Ingress Controller (traffic management)

### Phase 3: Optimization
- [ ] Parallel cluster upgrades within batch
- [ ] Canary upgrade strategy
- [ ] Web UI for monitoring
- [ ] Slack bot integration
- [ ] Automated batch progression

### Phase 4: Advanced
- [ ] Multi-region coordination
- [ ] Blue/green control plane upgrades
- [ ] Other service mesh support (Linkerd, Consul)
- [ ] Version compatibility checking
- [ ] Historical analytics
- [ ] Multi-service coordinated upgrades

### Phase 5: Intelligence
- [ ] LLM-powered failure prediction
- [ ] Automatic SLO-based thresholds
- [ ] Incident management integration
- [ ] Self-healing capabilities

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/contributing.md) for guidelines.

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/your-org/igu/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/igu/discussions)
- **Slack**: #igu-support

---

## License

Apache 2.0 - see [LICENSE](LICENSE)

---

## Acknowledgments

Built with ❤️ by Platform Engineering

Special thanks to:
- The Istio community
- FluxCD maintainers
- Datadog for observability
- All contributors

---

## Related Projects

- [Istio](https://istio.io/) - Service mesh
- [FluxCD](https://fluxcd.io/) - GitOps toolkit
- [kubectl](https://kubernetes.io/docs/reference/kubectl/) - Kubernetes CLI
- [istioctl](https://istio.io/latest/docs/reference/commands/istioctl/) - Istio CLI

---

<div align="center">

**[⬆ back to top](#istio-gitops-upgrader-igu)**

</div>
