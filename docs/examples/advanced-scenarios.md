# Advanced Usage Scenarios

This document covers advanced usage patterns and complex scenarios for GUARD.

## Table of Contents

- [Multi-Region Coordination](#multi-region-coordination)
- [Canary Upgrades](#canary-upgrades)
- [LLM-Powered Failure Analysis](#llm-powered-failure-analysis)
- [Custom Health Checks](#custom-health-checks)
- [Custom Datadog Queries](#custom-datadog-queries)
- [Batch Dependencies](#batch-dependencies)
- [Zero-Downtime Upgrades](#zero-downtime-upgrades)
- [Integration with CI/CD](#integration-with-cicd)
- [Multi-Tenancy](#multi-tenancy)

## Multi-Region Coordination

Coordinate upgrades across multiple AWS regions:

```yaml
# ~/.guard/config.yaml
batches:
  # US East region
  - name: us-east-prod-wave-1
    description: Production US East - Critical
    clusters:
      - eks-prod-us-east-1-api
      - eks-prod-us-east-1-web

  # US West region (only after US East succeeds)
  - name: us-west-prod-wave-1
    description: Production US West - Critical
    clusters:
      - eks-prod-us-west-2-api
      - eks-prod-us-west-2-web

  # EU region (only after US regions succeed)
  - name: eu-prod-wave-1
    description: Production EU - Critical
    clusters:
      - eks-prod-eu-west-1-api
      - eks-prod-eu-west-1-web

# Define batch order
batch_order:
  us-west-prod-wave-1:
    - us-east-prod-wave-1  # US West requires US East first
  eu-prod-wave-1:
    - us-east-prod-wave-1  # EU requires US East first
    - us-west-prod-wave-1  # EU requires US West first
```

```bash
# Automated script for multi-region rollout
#!/bin/bash
set -e

TARGET_VERSION="1.20.0"

# Region 1: US East (Primary)
echo "=== US East Region ==="
guard run --batch us-east-prod-wave-1 --target-version $TARGET_VERSION
echo "Review and merge MR, then press Enter..."
read
guard monitor --batch us-east-prod-wave-1 --soak-period 120

# Region 2: US West (wait for US East)
echo "=== US West Region ==="
guard run --batch us-west-prod-wave-1 --target-version $TARGET_VERSION
echo "Review and merge MR, then press Enter..."
read
guard monitor --batch us-west-prod-wave-1 --soak-period 120

# Region 3: EU (wait for both US regions)
echo "=== EU Region ==="
guard run --batch eu-prod-wave-1 --target-version $TARGET_VERSION
echo "Review and merge MR, then press Enter..."
read
guard monitor --batch eu-prod-wave-1 --soak-period 120

echo "✓ Multi-region upgrade complete!"
```

## Canary Upgrades

Upgrade a single "canary" cluster first:

```yaml
# ~/.guard/config.yaml
batches:
  - name: prod-canary
    description: Production canary (5% of traffic)
    clusters:
      - eks-prod-us-east-1-canary

  - name: prod-main
    description: Production main clusters
    clusters:
      - eks-prod-us-east-1-api-1
      - eks-prod-us-east-1-api-2
      - eks-prod-us-east-1-api-3
```

```bash
# 1. Upgrade canary first
guard run --batch prod-canary --target-version 1.20.0
guard monitor --batch prod-canary --soak-period 240  # Long soak (4 hours)

# 2. If canary successful, upgrade main
if [ $? -eq 0 ]; then
    echo "Canary successful, proceeding with main clusters"
    guard run --batch prod-main --target-version 1.20.0
    guard monitor --batch prod-main --soak-period 120
else
    echo "Canary failed, aborting main cluster upgrade"
    guard rollback --batch prod-canary
    exit 1
fi
```

## LLM-Powered Failure Analysis

Enable AI-powered failure investigation:

```yaml
# ~/.guard/config.yaml
llm:
  enabled: true
  provider: openai  # or anthropic
  model: gpt-4
  api_key_secret: guard/llm-api-key
```

```bash
# Store LLM API key
aws secretsmanager create-secret \
    --name guard/llm-api-key \
    --secret-string "sk-xxxxxxxxxxxxx"

# Run upgrade with LLM analysis on failure
guard run --batch prod-wave-1 --target-version 1.20.0
guard monitor --batch prod-wave-1 --enable-llm-analysis

# If validation fails, GUARD will:
# 1. Collect failure data (metrics, logs, events)
# 2. Send to LLM for analysis
# 3. Include analysis in rollback MR
```

Example LLM analysis output:

```markdown
## AI Failure Analysis

### Summary
The upgrade validation failed due to a 25% increase in P95 latency.

### Root Cause Analysis
Based on the collected metrics and logs, the likely root cause is:

1. **New Istio version introduced connection pooling changes**
   - Default connection timeout reduced from 60s to 30s
   - Causing more connection resets under load

2. **Supporting Evidence**
   - Spike in `istio_tcp_connections_closed_total` metric (+40%)
   - Increase in `upstream_rq_timeout` errors
   - No corresponding increase in application errors

### Recommended Actions
1. Adjust Istio connection timeout via DestinationRule:
   ```yaml
   spec:
     trafficPolicy:
       connectionPool:
         tcp:
           connectTimeout: 60s  # Restore previous timeout
   ```

2. Or upgrade application to handle shorter timeouts

3. Re-validate after confguardration change
```

## Custom Health Checks

Add custom health checks:

```python
# custom_checks.py
from guard.checks.base import HealthCheck
from guard.core.models import HealthCheckResult, CheckStatus, Cluster

class CustomDatabaseCheck(HealthCheck):
    """Check database connectivity from cluster."""

    async def run(self, cluster: Cluster) -> HealthCheckResult:
        """Run database connectivity check."""
        try:
            # Connect to database via cluster
            # Run test query
            # Check query performance

            return HealthCheckResult(
                cluster_id=cluster.cluster_id,
                check_name="database_connectivity",
                status=CheckStatus.PASS,
                message="Database connectivity healthy",
                timestamp=datetime.now(),
                details={
                    "query_time_ms": 45,
                    "connection_pool_usage": "23%"
                }
            )
        except Exception as e:
            return HealthCheckResult(
                cluster_id=cluster.cluster_id,
                check_name="database_connectivity",
                status=CheckStatus.FAIL,
                message=f"Database check failed: {e}",
                timestamp=datetime.now(),
                details={"error": str(e)}
            )
```

```yaml
# ~/.guard/config.yaml
custom_checks:
  - module: custom_checks
    class: CustomDatabaseCheck
```

## Custom Datadog Queries

Define custom metrics for validation:

```yaml
# ~/.guard/config.yaml
datadog:
  queries:
    # Standard queries
    error_rate: "sum:trace.http.request.errors{env:{environment}}.as_count() / sum:trace.http.request.hits{env:{environment}}.as_count()"
    latency_p95: "avg:trace.http.request.duration.by.service.95p{env:{environment}}"

    # Custom queries
    custom_api_success_rate: "sum:custom.api.success{cluster:{cluster_name}}.as_count() / sum:custom.api.total{cluster:{cluster_name}}.as_count()"
    custom_cache_hit_rate: "sum:custom.cache.hits{cluster:{cluster_name}}.as_count() / sum:custom.cache.requests{cluster:{cluster_name}}.as_count()"
    custom_queue_depth: "avg:custom.queue.depth{cluster:{cluster_name}}"

validation:
  thresholds:
    # Standard thresholds
    latency_increase_percent: 10
    error_rate_max: 0.001

    # Custom thresholds
    custom_api_success_rate_min: 0.999  # Min 99.9% success rate
    custom_cache_hit_rate_min: 0.80     # Min 80% cache hit rate
    custom_queue_depth_max: 1000        # Max queue depth of 1000
```

## Batch Dependencies

Complex batch ordering with dependencies:

```yaml
# ~/.guard/config.yaml
batches:
  - name: test
    description: Test cluster
    clusters: [eks-test]

  - name: dev-1
    description: Dev wave 1
    clusters: [eks-dev-1, eks-dev-2]

  - name: dev-2
    description: Dev wave 2
    clusters: [eks-dev-3, eks-dev-4]

  - name: staging-us
    description: Staging US
    clusters: [eks-staging-us-east-1, eks-staging-us-west-2]

  - name: staging-eu
    description: Staging EU
    clusters: [eks-staging-eu-west-1]

  - name: prod-canary
    description: Production canary
    clusters: [eks-prod-canary]

  - name: prod-us-1
    description: Production US - Critical
    clusters: [eks-prod-us-api, eks-prod-us-web]

  - name: prod-us-2
    description: Production US - Remaining
    clusters: [eks-prod-us-app1, eks-prod-us-app2]

  - name: prod-eu
    description: Production EU
    clusters: [eks-prod-eu-api, eks-prod-eu-web]

# Dependency graph
batch_order:
  dev-1: [test]                           # Dev 1 needs test
  dev-2: [dev-1]                          # Dev 2 needs dev 1
  staging-us: [dev-1, dev-2]              # Staging US needs both dev waves
  staging-eu: [dev-1, dev-2]              # Staging EU needs both dev waves
  prod-canary: [staging-us, staging-eu]   # Canary needs all staging
  prod-us-1: [prod-canary]                # Prod US 1 needs canary
  prod-us-2: [prod-us-1]                  # Prod US 2 needs prod US 1
  prod-eu: [prod-us-1]                    # Prod EU needs prod US 1
```

```bash
# Automated dependency-aware rollout
#!/bin/bash
set -e

TARGET_VERSION="1.20.0"

# Function to run batch
run_batch() {
    local batch=$1
    echo "=== Upgrading batch: $batch ==="
    guard run --batch $batch --target-version $TARGET_VERSION
    echo "Review and merge MR for $batch, then press Enter..."
    read
    guard monitor --batch $batch

    if [ $? -ne 0 ]; then
        echo "ERROR: Batch $batch failed validation"
        exit 1
    fi
}

# Execute in dependency order
run_batch "test"
run_batch "dev-1"
run_batch "dev-2"
run_batch "staging-us"
run_batch "staging-eu"
run_batch "prod-canary"
run_batch "prod-us-1"
run_batch "prod-us-2"
run_batch "prod-eu"

echo "✓ All batches upgraded successfully!"
```

## Zero-Downtime Upgrades

Ensure zero downtime during upgrades:

```yaml
# ~/.guard/config.yaml
execution:
  enable_rollout_sequencing: true
  pod_disruption_budget_required: true
  min_ready_replicas_percent: 80  # Always keep 80% of pods ready
```

```bash
# GUARD ensures:
# 1. PodDisruptionBudget exists
# 2. Rolling update strategy confguardred
# 3. Sufficient replicas available
# 4. Traffic shift gradual

# Example validation
guard run --batch prod-wave-1 --target-version 1.20.0 \
    --ensure-pdb \
    --min-replicas 3 \
    --max-unavailable 1
```

## Integration with CI/CD

### GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - upgrade
  - validate

variables:
  GUARD_VERSION: "1.20.0"

upgrade-test:
  stage: upgrade
  script:
    - pip install guard
    - guard run --batch test --target-version $GUARD_VERSION
    - guard monitor --batch test
  only:
    - schedules
  environment:
    name: test

upgrade-prod:
  stage: upgrade
  script:
    - pip install guard
    - guard run --batch prod-wave-1 --target-version $GUARD_VERSION
    # Wait for manual MR merge
  when: manual
  only:
    - schedules
  environment:
    name: production

validate-prod:
  stage: validate
  script:
    - pip install guard
    - guard monitor --batch prod-wave-1 --soak-period 120
  needs: [upgrade-prod]
  environment:
    name: production
```

### GitHub Actions

```yaml
# .github/workflows/istio-upgrade.yml
name: Istio Upgrade

on:
  schedule:
    - cron: '0 2 * * 1'  # Every Monday at 2 AM
  workflow_dispatch:
    inputs:
      target_version:
        description: 'Target Istio version'
        required: true
      batch:
        description: 'Batch to upgrade'
        required: true

jobs:
  upgrade:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install GUARD
        run: pip install guard

      - name: Confguardre AWS
        uses: aws-actions/confguardre-aws-credentials@v2
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Run pre-checks and create MR
        run: |
          guard run --batch ${{ inputs.batch }} \
                  --target-version ${{ inputs.target_version }}

      - name: Wait for MR merge
        run: |
          echo "Review and merge the GitLab MR"
          echo "Then manually trigger the validation job"

  validate:
    runs-on: ubuntu-latest
    needs: upgrade
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install GUARD
        run: pip install guard

      - name: Confguardre AWS
        uses: aws-actions/confguardre-aws-credentials@v2
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Monitor and validate
        run: |
          guard monitor --batch ${{ inputs.batch }} --soak-period 120

      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "Istio upgrade validation failed for batch ${{ inputs.batch }}"
            }
```

## Multi-Tenancy

Manage upgrades for multiple teams/tenants:

```yaml
# ~/.guard/team-a-config.yaml
aws:
  region: us-east-1
  dynamodb:
    table_name: guard-cluster-registry
  secrets_manager:
    gitlab_token_secret: guard/team-a/gitlab-token
    datadog_credentials_secret: guard/team-a/datadog-credentials

batches:
  - name: team-a-prod
    description: Team A production clusters
    clusters:
      - eks-team-a-prod-1
      - eks-team-a-prod-2
```

```bash
# Team A upgrade
guard run --config ~/.guard/team-a-config.yaml \
    --batch team-a-prod \
    --target-version 1.20.0

# Team B upgrade (separate config)
guard run --config ~/.guard/team-b-config.yaml \
    --batch team-b-prod \
    --target-version 1.20.0
```

## Parallel Batch Execution

Upgrade multiple independent batches in parallel:

```bash
#!/bin/bash

# Upgrade dev batches in parallel (they're independent)
guard run --batch dev-us-east --target-version 1.20.0 &
PID1=$!

guard run --batch dev-us-west --target-version 1.20.0 &
PID2=$!

guard run --batch dev-eu --target-version 1.20.0 &
PID3=$!

# Wait for all to complete
wait $PID1 $PID2 $PID3

echo "All dev batches ready for MR merge"
```
