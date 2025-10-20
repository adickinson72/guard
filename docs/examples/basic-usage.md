# Basic Usage Examples

This document provides common usage examples for GUARD (GitOps Upgrade Automation with Rollback Detection).

## Table of Contents

- [Single Cluster Upgrade](#single-cluster-upgrade)
- [Batch Upgrade](#batch-upgrade)
- [Dry Run Mode](#dry-run-mode)
- [Custom Validation Thresholds](#custom-validation-thresholds)
- [Manual Rollback](#manual-rollback)
- [Listing Clusters](#listing-clusters)
- [Checking Cluster Status](#checking-cluster-status)

## Single Cluster Upgrade

Upgrade a single test cluster:

```bash
# 1. Create a batch with one cluster
cat > ~/.guard/config.yaml <<EOF
batches:
  - name: single-test
    description: Single test cluster
    clusters:
      - eks-test-us-east-1
EOF

# 2. Run pre-checks and create MR
igu run --batch single-test --target-version 1.20.0

# Expected output:
# Running pre-upgrade health checks...
# ✓ All pre-checks passed
# MR created: https://gitlab.com/.../merge_requests/123

# 3. Review and merge MR in GitLab

# 4. Monitor upgrade
igu monitor --batch single-test

# Expected output:
# Waiting for Flux sync...
# ✓ Flux synced
# Monitoring rollout...
# ✓ All pods ready
# Running validation...
# ✓ Validation passed
```

## Batch Upgrade

Upgrade multiple clusters in a batch:

```yaml
# ~/.guard/config.yaml
batches:
  - name: dev-wave-1
    description: Development clusters - wave 1
    clusters:
      - eks-dev-us-east-1-app1
      - eks-dev-us-east-1-app2
      - eks-dev-us-east-1-app3
```

```bash
# Run upgrade for entire batch
igu run --batch dev-wave-1 --target-version 1.20.0

# Output shows checks for all clusters:
# Cluster: eks-dev-us-east-1-app1
#   ✓ Kubernetes health
#   ✓ Istio health
#   ✓ Datadog metrics
# Cluster: eks-dev-us-east-1-app2
#   ✓ Kubernetes health
#   ✓ Istio health
#   ✓ Datadog metrics
# ...

# Monitor all clusters
igu monitor --batch dev-wave-1
```

## Dry Run Mode

Test the upgrade workflow without making changes:

```bash
# Dry run - runs checks but doesn't create MR
igu run --batch prod-wave-1 --target-version 1.20.0 --dry-run

# Output:
# [DRY RUN] Running pre-checks...
# ✓ All checks passed
# [DRY RUN] Would create MR with:
#   - Branch: igu/upgrade-istio-1.20.0-prod-wave-1
#   - Clusters: 3
#   - Changes: [shows Flux config diffs]
# [DRY RUN] No MR created (dry run mode)
```

## Custom Validation Thresholds

Override default validation thresholds:

```bash
# Use stricter thresholds for production
igu run --batch prod-wave-1 --target-version 1.20.0 \
    --latency-threshold 5 \
    --error-rate-threshold 0.0005 \
    --resource-threshold 25

# Monitor with custom thresholds
igu monitor --batch prod-wave-1 \
    --soak-period 120 \
    --latency-threshold 5
```

Or configure in YAML:

```yaml
# ~/.guard/config.yaml
validation:
  soak_period_minutes: 120
  thresholds:
    latency_increase_percent: 5    # Only 5% increase allowed
    error_rate_max: 0.0005         # Max 0.05% error rate
    resource_increase_percent: 25  # Only 25% resource increase
```

## Manual Rollback

Trigger a rollback if needed:

```bash
# Rollback a specific cluster
igu rollback --cluster eks-prod-us-east-1-api

# Output:
# Creating rollback MR...
# Reverting from 1.20.0 to 1.19.3
# ✓ Rollback MR created: https://gitlab.com/.../merge_requests/124
# Review and merge to complete rollback

# Or rollback entire batch
igu rollback --batch prod-wave-1
```

## Listing Clusters

List clusters and their status:

```bash
# List all clusters
igu list

# Output:
# Batch: test
#   - eks-test-us-east-1 (healthy, Istio 1.19.3)
#
# Batch: dev-wave-1
#   - eks-dev-us-east-1-app1 (healthy, Istio 1.20.0)
#   - eks-dev-us-east-1-app2 (healthy, Istio 1.20.0)
#   - eks-dev-us-east-1-app3 (upgrading, Istio 1.19.3 → 1.20.0)
#
# Batch: prod-wave-1
#   - eks-prod-us-east-1-api (healthy, Istio 1.19.3)
#   - eks-prod-us-east-1-web (healthy, Istio 1.19.3)

# List specific batch
igu list --batch prod-wave-1

# List with details
igu list --batch prod-wave-1 --verbose

# Output includes:
# Cluster: eks-prod-us-east-1-api
#   Batch: prod-wave-1
#   Environment: production
#   Region: us-east-1
#   Current Version: 1.19.3
#   Status: healthy
#   Owner: @platform-team
#   Last Updated: 2024-10-15 14:23:45
```

## Checking Cluster Status

Get detailed status for a specific cluster:

```bash
# Show cluster details
igu registry show eks-prod-us-east-1-api

# Output:
# Cluster ID: eks-prod-us-east-1-api
# Batch: prod-wave-1
# Environment: production
# Region: us-east-1
# GitLab Repo: infra/k8s-clusters
# Flux Config: clusters/prod/us-east-1/api/istio-helmrelease.yaml
# AWS Role: arn:aws:iam::123456789:role/GUARD-EKSAccess
# Current Istio Version: 1.19.3
# Status: healthy
# Owner Team: platform-engineering
# Owner Handle: @platform-team
# Datadog Tags:
#   cluster: eks-prod-us-east-1-api
#   service: istio-system
#   env: production

# Check health without upgrading
igu check --cluster eks-prod-us-east-1-api

# Output:
# Running health checks...
# ✓ Kubernetes API healthy
# ✓ Istio control plane healthy
# ✓ No configuration issues (istioctl analyze)
# ✓ Datadog metrics normal
# ✓ No active alerts
```

## Progressive Rollout

Upgrade clusters progressively across environments:

```bash
# 1. Test cluster
igu run --batch test --target-version 1.20.0
# Review and merge MR
igu monitor --batch test

# 2. Dev wave 1
igu run --batch dev-wave-1 --target-version 1.20.0
igu monitor --batch dev-wave-1

# 3. Dev wave 2
igu run --batch dev-wave-2 --target-version 1.20.0
igu monitor --batch dev-wave-2

# 4. Staging
igu run --batch staging --target-version 1.20.0
igu monitor --batch staging --soak-period 120  # Longer soak

# 5. Prod wave 1 (critical services)
igu run --batch prod-wave-1 --target-version 1.20.0
igu monitor --batch prod-wave-1 --soak-period 120

# 6. Prod wave 2 (remaining services)
igu run --batch prod-wave-2 --target-version 1.20.0
igu monitor --batch prod-wave-2 --soak-period 120
```

## Verbose Logging

Enable detailed logging for troubleshooting:

```bash
# Run with debug logging
igu run --batch prod-wave-1 --target-version 1.20.0 --verbose

# Or set environment variable
export GUARD_LOG_LEVEL=DEBUG
igu run --batch prod-wave-1 --target-version 1.20.0

# Output includes:
# DEBUG: Loading config from /home/user/.igu/config.yaml
# DEBUG: Connecting to DynamoDB table: igu-cluster-registry
# DEBUG: Querying clusters for batch: prod-wave-1
# DEBUG: Found 2 clusters
# DEBUG: Assuming role: arn:aws:iam::123:role/GUARD-EKSAccess
# DEBUG: Connecting to EKS cluster: eks-prod-us-east-1-api
# ...
```

## Validation Only

Run validation without pre-checks or MR creation:

```bash
# Useful after manually merging an upgrade MR
igu monitor --batch prod-wave-1 --skip-sync-wait

# Or validate a specific cluster
igu validate-cluster eks-prod-us-east-1-api \
    --baseline-file baseline-metrics.json
```

## Configuration Validation

Validate your configuration before running upgrades:

```bash
# Validate config file
igu validate --config ~/.guard/config.yaml

# Output:
# ✓ Configuration file is valid
# ✓ AWS credentials valid
# ✓ DynamoDB table accessible: igu-cluster-registry
# ✓ GitLab credentials valid
# ✓ GitLab API accessible: https://gitlab.company.com
# ✓ Datadog credentials valid
# ✓ Datadog API accessible
# ✓ All secrets accessible:
#     - igu/gitlab-token
#     - igu/datadog-credentials
# ✓ All batches have valid clusters
# ✓ Flux config paths exist in GitLab repos
#
# Configuration is valid!
```

## Export Health Report

Export health check results for documentation:

```bash
# Run checks and export to file
igu run --batch prod-wave-1 --target-version 1.20.0 \
    --export-health-report health-report.json

# View report
cat health-report.json

# Output (JSON):
# {
#   "batch_id": "prod-wave-1",
#   "target_version": "1.20.0",
#   "timestamp": "2024-10-18T10:30:00Z",
#   "clusters": {
#     "eks-prod-us-east-1-api": {
#       "checks": [
#         {
#           "name": "kubernetes_health",
#           "status": "PASS",
#           "message": "Kubernetes API healthy",
#           "details": {...}
#         },
#         ...
#       ]
#     }
#   }
# }
```

## Using Alternative Config File

Use a different config file:

```bash
# Use custom config
igu run --batch prod-wave-1 --target-version 1.20.0 \
    --config /path/to/custom-config.yaml

# Or set environment variable
export GUARD_CONFIG_PATH=/path/to/custom-config.yaml
igu run --batch prod-wave-1 --target-version 1.20.0
```

## Notification Integration

Configure notifications for upgrade events:

```yaml
# ~/.guard/config.yaml
rollback:
  notification:
    enabled: true
    webhook_url: https://hooks.slack.com/services/XXX/YYY/ZZZ
```

```bash
# Notifications sent automatically on:
# - Pre-check failures
# - Validation failures
# - Rollback creation
# - Upgrade completion

# Example Slack message:
# ⚠️ GUARD Alert: Validation Failed
# Cluster: eks-prod-us-east-1-api
# Batch: prod-wave-1
# Reason: Latency increased 25% (threshold: 10%)
# Rollback MR created: https://gitlab.com/.../merge_requests/125
```

## Registry Management

Manage cluster registry:

```bash
# Add new cluster
igu registry add \
    --cluster-id eks-prod-us-west-2-api \
    --batch-id prod-wave-2 \
    --environment production \
    --region us-west-2 \
    --gitlab-repo infra/k8s-clusters \
    --flux-config-path clusters/prod/us-west-2/api/istio.yaml \
    --aws-role-arn arn:aws:iam::123:role/GUARD-Access \
    --current-version 1.19.3

# Update cluster
igu registry update eks-prod-us-west-2-api \
    --current-version 1.20.0 \
    --status healthy

# Remove cluster
igu registry remove eks-old-cluster

# Import from JSON
igu registry import --file clusters.json

# Export to JSON
igu registry export --output clusters-backup.json
```
