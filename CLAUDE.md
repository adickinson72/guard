# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GUARD (GitOps Upgrade Automation with Rollback Detection)** automates safe, progressive Istio upgrades across 75+ EKS clusters using GitOps workflows. The system performs automated pre-checks, creates GitLab merge requests, validates post-upgrade health, and triggers rollbacks when needed.

## Development Commands

### Setup
```bash
# Install dependencies with Poetry
poetry install

# Install pre-commit hooks
poetry run pre-commit install
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage (90%+ required)
pytest --cov=guard --cov-report=html

# Run specific test types
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests (requires credentials)
pytest tests/e2e/               # End-to-end tests

# Run with markers
pytest -m "not slow"            # Skip slow tests
pytest -m integration           # Integration tests only
pytest -m "not integration"     # Skip integration tests (unit tests only)

# Run specific integration test suites
pytest tests/integration/test_aws_client_integration.py
pytest tests/integration/test_gitlab_client_integration.py
pytest tests/integration/test_kubernetes_client_integration.py
pytest tests/integration/test_datadog_client_integration.py

# Run a single test file
pytest tests/unit/test_cluster_registry.py

# Run a single test function
pytest tests/unit/test_cluster_registry.py::test_get_clusters_by_batch
```

#### Integration Test Requirements

Integration tests require credentials for external services. Tests will skip automatically if credentials are not available.

**Required Environment Variables:**
```bash
# AWS Integration Tests
export AWS_TEST_REGION="us-east-1"
export AWS_TEST_ROLE_ARN="arn:aws:iam::123:role/TestRole"  # Optional

# GitLab Integration Tests
export GITLAB_TEST_TOKEN="glpat-xxxxxxxxxxxxx"
export GITLAB_TEST_PROJECT_ID="group/project"              # Optional
export GITLAB_TEST_ALLOW_WRITE="true"                      # Optional, enables write tests

# Kubernetes Integration Tests (uses ~/.kube/config by default)
export KUBECONFIG="/path/to/kubeconfig"                    # Optional
export K8S_TEST_CONTEXT="my-test-cluster"                  # Optional

# Datadog Integration Tests
export DATADOG_TEST_API_KEY="xxxxxxxxxxxxx"
export DATADOG_TEST_APP_KEY="xxxxxxxxxxxxx"
```

See [tests/integration/README.md](tests/integration/README.md) for detailed integration test documentation.

### Code Quality
```bash
# Lint with ruff
poetry run ruff check .

# Format code
poetry run ruff format .

# Type checking with mypy
poetry run mypy src/

# Run all quality checks (pre-commit)
poetry run pre-commit run --all-files
```

### Building and Running
```bash
# Build Docker image
docker build -t guard:local .

# Run CLI locally
poetry run guard --help
poetry run guard validate --config ~/.guard/config.yaml
poetry run guard list --batch test
poetry run guard run --batch test --target-version 1.20.0

# Run in Kubernetes (after deploying)
kubectl exec -n guard-system deploy/guard -- guard run --batch prod-wave-1 --target-version 1.20.0
```

### Kubernetes Deployment
```bash
# Deploy using Kustomize
kubectl apply -k k8s/

# View logs
kubectl logs -n guard-system deploy/guard -f

# Check all resources
kubectl get all -n guard-system
```

## Architecture

### Source Code Structure
```
src/guard/
├── cli/              # Click-based CLI commands (run, monitor, rollback, list, validate)
├── clients/          # External service clients
│   ├── aws_client.py       # AWS STS, EKS, Secrets Manager interactions
│   ├── kubernetes_client.py # K8s API for cluster state and pod management
│   ├── datadog_client.py   # Datadog metrics, monitors, and alerts
│   ├── gitlab_client.py    # GitLab MR creation and branch management
│   └── istioctl.py         # Wrapper for istioctl analyze commands
├── core/             # Core models and configuration
│   ├── models.py           # Pydantic models (ClusterConfig, CheckResult, etc.)
│   ├── config.py           # Application configuration management
│   └── exceptions.py       # Custom exception classes
├── registry/         # Cluster registry management (DynamoDB-backed)
├── checks/           # Pre-upgrade health checks
│   └── pre_check_engine.py # Validates K8s, Istio, and Datadog state
├── validation/       # Post-upgrade validation logic
├── gitops/           # GitLab MR creation and Flux config updates
├── rollback/         # Automated rollback operations
├── llm/              # Optional LLM-powered failure analysis
│   ├── analyzer.py
│   └── prompts.py
└── utils/            # Logging, rate limiting, and utilities
```

### Key Workflows

1. **Pre-Check Phase**: `checks/pre_check_engine.py` validates cluster health
   - Kubernetes control plane status via `clients/kubernetes_client.py`
   - Istio configuration via `clients/istioctl.py` (istioctl analyze)
   - Datadog metrics baseline via `clients/datadog_client.py`
   - Active alert detection

2. **GitOps Phase**: `gitops/` creates merge requests
   - Updates Flux HelmRelease YAML with target Istio version
   - Creates feature branch and MR via `clients/gitlab_client.py`
   - Human approval gate (manual MR merge)

3. **Post-Upgrade Validation**: `validation/` monitors after deployment
   - Waits for soak period (configurable, default 60 minutes)
   - Compares metrics pre/post upgrade
   - Validates pod health and sidecar versions
   - Triggers rollback on failure

4. **Rollback**: `rollback/` creates rollback MR automatically
   - Reverts Flux config to previous Istio version
   - Creates emergency MR with rollback changes

### State Management

- **DynamoDB**: Cluster registry stores `ClusterConfig` objects
- **Status Tracking**: Clusters progress through states defined in `core/models.py::ClusterStatus`
  - PENDING → PRE_CHECK_RUNNING → PRE_CHECK_PASSED → MR_CREATED → UPGRADING → POST_CHECK_RUNNING → HEALTHY
  - Failures branch to ROLLBACK_REQUIRED or FAILED_UPGRADE_ROLLED_BACK

### Multi-Cluster Strategy

- **Batch System**: Clusters grouped by batch_id (test, dev-wave-1, staging, prod-wave-1, etc.)
- **Progressive Rollout**: Upgrade test → dev → staging → prod in controlled waves
- **Fail-Fast**: Batch upgrade halts if any cluster fails pre-checks

## Testing Philosophy

This project follows **Test-Driven Development (TDD)**:
1. Write tests first (red)
2. Write minimal code to pass (green)
3. Refactor while keeping tests passing

### Test Coverage Requirements
- Unit tests: 90%+ coverage (enforced in pyproject.toml)
- All external service interactions must have integration tests
- Critical workflows need E2E tests

### Test Structure
- `tests/unit/`: Fast, isolated tests with mocked dependencies
- `tests/integration/`: Tests with real external service calls (AWS, Datadog, GitLab)
- `tests/e2e/`: Full workflow simulations
- `tests/conftest.py`: Shared fixtures (mock clients, sample data)

### Writing Tests
- Use fixtures from `conftest.py` for common test data
- Mock external clients (`mock_kubernetes_client`, `mock_datadog_client`, etc.)
- Test unhappy paths and edge cases
- Use pytest markers for categorization (`@pytest.mark.requires_aws`)

## Configuration

### Required Credentials
- **GitLab PAT**: Stored in AWS Secrets Manager as `guard/gitlab-token`
- **Datadog API/App Keys**: Stored in AWS Secrets Manager as `guard/datadog-credentials`
- **AWS IAM Roles**: Cross-account roles for EKS cluster access (defined per cluster in registry)

### Configuration Files
- `~/.guard/config.yaml`: Main configuration (see `examples/config.yaml.example`)
- DynamoDB table: `guard-cluster-registry` (created via `scripts/setup-dynamodb.sh`)

### Kubernetes Deployment Configuration
- `k8s/serviceaccount.yaml`: Pod Identity for cross-account AWS access
- `k8s/configmap.yaml`: ConfigMap with GUARD configuration
- `k8s/deployment.yaml`: Long-running GUARD pod for manual execution
- `k8s/cronjob.yaml`: Scheduled upgrade automation

## Code Standards

### Type Hints
- All functions must have type hints (enforced by mypy)
- Use `from __future__ import annotations` for forward references
- Prefer `str | None` over `Optional[str]` (Python 3.11+ union syntax)

### Models
- Use Pydantic v2 for data validation
- Define models in `core/models.py` or co-located with functionality
- Use `Field()` for descriptions and validation

### Error Handling
- Custom exceptions defined in `core/exceptions.py`
- Structured logging via `structlog` (configured in `utils/logging.py`)
- Use tenacity for retries with exponential backoff

### Formatting
- Line length: 100 characters
- Ruff for linting and formatting (Black-compatible)
- Import order: stdlib → third-party → first-party (`guard`)

## Important Implementation Details

### AWS Cross-Account Access
- Uses STS AssumeRole via `clients/aws_client.py`
- IAM roles must trust the execution role (EKS Pod Identity or local role)
- Temporary credentials cached per session

### Istio Sidecar Restart
After control plane upgrade, all pods with sidecars must be restarted:
- Query namespaces with `istio-injection=enabled` label
- Rolling restart of Deployments, StatefulSets, DaemonSets
- Ensures sidecar proxy versions match new control plane

### Datadog Integration
- Query metrics using `clients/datadog_client.py`
- Baseline metrics captured before upgrade
- Post-upgrade comparison with configurable thresholds (`core/models.py::ValidationThresholds`)
- Alert detection prevents upgrades during active incidents

### GitLab MR Automation
- Branch naming: `feature/istio-{version}-{batch_id}`
- MR title: "Istio upgrade to v{version} for {batch_id}"
- Automated Flux HelmRelease YAML updates (version change only)
- Requires human approval before merge (safety gate)

## Common Pitfalls

### DynamoDB Schema
- `cluster_id` is the primary key (must be unique)
- `batch_id` is a GSI for batch-based queries
- Use `ClusterConfig.model_dump()` for serialization to DynamoDB

### Kubectl Context
- CLI assumes kubectl context is set correctly for target cluster
- In Kubernetes deployment, Pod Identity handles authentication
- Local execution requires AWS credentials and kubectl config

### Istioctl Analyze
- Must be run with appropriate kubeconfig context
- Returns structured YAML output (parsed by `clients/istioctl.py`)
- May fail if Istio CRDs are not installed

### Rate Limiting
- GitLab API: 600 requests/minute (handled by `utils/rate_limiter.py`)
- Datadog API: Varies by endpoint (client handles retries)
- Use tenacity decorators for automatic retry logic

## Dependencies

### Core
- **Click**: CLI framework
- **Pydantic v2**: Data validation and settings
- **Rich**: Terminal formatting and progress displays
- **structlog**: Structured logging

### AWS
- **boto3**: AWS SDK (DynamoDB, STS, Secrets Manager, EKS)
- **boto3-stubs**: Type stubs for mypy

### Kubernetes & Istio
- **kubernetes**: Official Python client
- **istioctl**: Binary installed in Dockerfile (not Python package)

### External Services
- **python-gitlab**: GitLab API client
- **datadog-api-client**: Datadog API v2 client
- **httpx**: Async HTTP client

### Development
- **pytest**: Testing framework with plugins (pytest-cov, pytest-mock, pytest-asyncio)
- **mypy**: Static type checking
- **ruff**: Fast linter and formatter
- **pre-commit**: Git hooks for code quality
