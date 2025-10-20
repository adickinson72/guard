# Getting Started with GUARD

This guide will walk you through installing GUARD and performing your first Istio upgrade.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Initial Setup](#initial-setup)
- [Your First Upgrade](#your-first-upgrade)
- [Understanding the Workflow](#understanding-the-workflow)
- [Next Steps](#next-steps)

## Prerequisites

Before you begin, ensure you have:

### Required Tools

- **Python 3.11+**: [Download](https://www.python.org/downloads/)
- **kubectl**: [Installation guide](https://kubernetes.io/docs/tasks/tools/)
- **istioctl**: [Installation guide](https://istio.io/latest/docs/setup/getting-started/#download)
- **AWS CLI**: [Installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

### Required Access

- **AWS Account** with permissions for:
  - EKS (read access)
  - DynamoDB (read/write)
  - Secrets Manager (read)
  - STS (assume role)

- **GitLab Account** with:
  - Personal access token (API scope)
  - Access to infrastructure repository

- **Datadog Account** with:
  - API key
  - App key

### Verify Prerequisites

```bash
# Check Python version
python --version  # Should be 3.11 or higher

# Check kubectl
kubectl version --client

# Check istioctl
istioctl version --remote=false

# Check AWS CLI
aws --version
aws sts get-caller-identity  # Verify AWS credentials
```

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install igu
```

### Option 2: Install from Source

```bash
# Clone repository
git clone https://github.com/adickinson72/guard.git
cd igu

# Install with Poetry
curl -sSL https://install.python-poetry.org | python3 -
poetry install

# Or install with pip
pip install -e .
```

### Verify Installation

```bash
guard --version
guard --help
```

## Initial Setup

### Step 1: Create DynamoDB Table

Create a DynamoDB table for the cluster registry:

```bash
aws dynamodb create-table \
    --table-name guard-cluster-registry \
    --attribute-definitions \
        AttributeName=cluster_id,AttributeType=S \
        AttributeName=batch_id,AttributeType=S \
    --key-schema \
        AttributeName=cluster_id,KeyType=HASH \
    --global-secondary-indexes \
        "IndexName=batch_id-index,KeySchema=[{AttributeName=batch_id,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5}" \
    --provisioned-throughput \
        ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1

# Or use the provided script
./scripts/setup-dynamodb.sh
```

### Step 2: Store Credentials in AWS Secrets Manager

#### GitLab Token

Create a GitLab personal access token:
1. Go to GitLab → Settings → Access Tokens
2. Create token with `api` and `write_repository` scopes
3. Store in Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --description "GitLab token for GUARD" \
    --secret-string "glpat-xxxxxxxxxxxx" \
    --region us-east-1
```

#### Datadog Credentials

Get your Datadog API and App keys:
1. Go to Datadog → Organization Settings → API Keys
2. Go to Datadog → Organization Settings → Application Keys
3. Store in Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name guard/datadog-credentials \
    --description "Datadog credentials for GUARD" \
    --secret-string '{
        "api_key": "your-datadog-api-key",
        "app_key": "your-datadog-app-key"
    }' \
    --region us-east-1
```

### Step 3: Create Configuration File

Create GUARD configuration directory and file:

```bash
# Create config directory
mkdir -p ~/.guard

# Copy example config
cp examples/config.yaml.example ~/.guard/config.yaml

# Edit configuration
nano ~/.guard/config.yaml
```

Update the following required fields:

```yaml
# ~/.guard/config.yaml
aws:
  region: us-east-1
  dynamodb:
    table_name: guard-cluster-registry
    region: us-east-1
  secrets_manager:
    gitlab_token_secret: guard/gitlab-token
    datadog_credentials_secret: guard/datadog-credentials

gitlab:
  url: https://gitlab.yourcompany.com  # Update with your GitLab URL
  default_target_branch: main

datadog:
  site: datadoghq.com  # Or datadoghq.eu for EU

# Add your batches (we'll start with a test batch)
batches:
  - name: test
    description: Test cluster for validation
    clusters:
      - your-test-cluster-id
```

### Step 4: Populate Cluster Registry

Add your first test cluster to the registry:

```bash
# Using CLI (example)
guard registry add \
    --cluster-id eks-test-us-east-1 \
    --batch-id test \
    --environment test \
    --region us-east-1 \
    --gitlab-repo infra/k8s-clusters \
    --flux-config-path clusters/test/us-east-1/istio-helmrelease.yaml \
    --aws-role-arn arn:aws:iam::123456789:role/GUARD-EKSAccess \
    --current-version 1.19.3

# Or import from JSON file
# 1. Create cluster data file
cat > clusters.json <<EOF
{
  "cluster_id": "eks-test-us-east-1",
  "batch_id": "test",
  "environment": "test",
  "region": "us-east-1",
  "gitlab_repo": "infra/k8s-clusters",
  "flux_config_path": "clusters/test/us-east-1/istio-helmrelease.yaml",
  "aws_role_arn": "arn:aws:iam::123456789:role/GUARD-EKSAccess",
  "current_istio_version": "1.19.3",
  "datadog_tags": {
    "cluster": "eks-test-us-east-1",
    "service": "istio-system",
    "env": "test"
  },
  "owner_team": "platform-engineering",
  "owner_handle": "@platform-team",
  "status": "healthy"
}
EOF

# 2. Import
guard registry import --file clusters.json
```

### Step 5: Validate Setup

Verify everything is configured correctly:

```bash
# Validate configuration
guard validate --config ~/.guard/config.yaml

# Expected output:
# ✓ Configuration file is valid
# ✓ AWS credentials are valid
# ✓ DynamoDB table accessible
# ✓ GitLab credentials valid
# ✓ Datadog credentials valid
# ✓ All secrets accessible

# List clusters
guard list --batch test

# Expected output:
# Batch: test
# Clusters:
#   - eks-test-us-east-1 (healthy, Istio 1.19.3)
```

## Your First Upgrade

Now let's perform your first Istio upgrade on the test cluster!

### Step 1: Run Pre-Checks

```bash
# Run pre-upgrade health checks
guard run --batch test --target-version 1.20.0

# This will:
# 1. Query cluster registry for 'test' batch
# 2. Run Kubernetes health checks
# 3. Run Istio health checks (istioctl analyze)
# 4. Query Datadog metrics baseline
# 5. Check for active alerts
# 6. Create GitLab merge request
```

**Example output:**

```
GUARD - GitOps Upgrade Automation with Rollback Detection
===========================

Loading configuration from ~/.guard/config.yaml
Found 1 cluster(s) in batch 'test'

Running pre-upgrade health checks...

Cluster: eks-test-us-east-1
  ✓ Kubernetes API healthy
  ✓ Istio control plane healthy
  ✓ No configuration issues found
  ✓ Datadog metrics within normal range
  ✓ No active alerts

All pre-checks passed!

Creating GitLab merge request...
✓ Branch created: guard/upgrade-istio-1.20.0-test-20241018
✓ Flux config updated
✓ Merge request created: https://gitlab.yourcompany.com/infra/k8s-clusters/-/merge_requests/123

Next steps:
1. Review the merge request
2. Verify health report and Datadog dashboards
3. Approve and merge the MR
4. Run: guard monitor --batch test
```

### Step 2: Review and Merge MR

1. Open the GitLab MR URL from the output
2. Review the changes:
   - Pre-upgrade health report
   - Flux HelmRelease version updates
   - Datadog dashboard links
3. Verify health report shows all checks passed
4. Approve and merge the MR

**The MR will look like:**

```markdown
## Istio Upgrade: 1.20.0

### Pre-Upgrade Health Report

**Batch**: test
**Clusters**: 1
**All checks**: ✓ PASSED

| Cluster | K8s Health | Istio Health | Metrics | Alerts |
|---------|-----------|--------------|---------|--------|
| eks-test-us-east-1 | ✓ | ✓ | ✓ | ✓ |

### Clusters in Batch
- eks-test-us-east-1 (current: 1.19.3)

### Datadog Links
- [Istio Dashboard](https://app.datadoghq.com/...)

### Checklist
- [ ] Review pre-upgrade health report
- [ ] Verify Datadog dashboards
- [ ] Approve and merge to proceed
```

### Step 3: Monitor Upgrade

After merging the MR, monitor the upgrade:

```bash
# Monitor upgrade and run post-upgrade validation
guard monitor --batch test --soak-period 60

# This will:
# 1. Wait for Flux to sync changes
# 2. Monitor pod rollout
# 3. Wait for soak period (60 minutes)
# 4. Query post-upgrade metrics
# 5. Compare with baseline
# 6. Validate against thresholds
```

**Example output:**

```
GUARD - Monitoring Upgrade
========================

Batch: test
Target version: 1.20.0

Waiting for Flux sync...
✓ Flux synced changes

Monitoring pod rollout...
  ✓ istiod-1-20-0-abc123 (1/1 ready)
  ✓ istio-ingressgateway-1-20-0-def456 (2/2 ready)

Soak period: 60 minutes
[====================] 100% (60/60 min)

Running post-upgrade validation...

Comparing metrics with baseline:

| Metric | Baseline | Current | Change | Status |
|--------|----------|---------|--------|--------|
| P95 Latency | 245ms | 248ms | +1.2% | ✓ |
| Error Rate | 0.02% | 0.02% | 0% | ✓ |
| CPU Usage | 45% | 47% | +4.4% | ✓ |
| Memory Usage | 2.1GB | 2.2GB | +4.8% | ✓ |

✓ All validations passed!

Upgrade completed successfully!
Cluster eks-test-us-east-1 is now running Istio 1.20.0
```

### Step 4: Verify in Kubernetes

Verify the upgrade in your cluster:

```bash
# Assume role and configure kubectl
aws eks update-kubeconfig --name eks-test-us-east-1 --region us-east-1

# Check Istio version
kubectl -n istio-system get pods -l app=istiod
istioctl version

# Expected output:
# client version: 1.20.0
# control plane version: 1.20.0
# data plane version: 1.20.0 (2 proxies)

# Verify health
istioctl analyze -n istio-system
# ✔ No validation issues found when analyzing namespace: istio-system.
```

🎉 **Congratulations!** You've successfully completed your first GUARD upgrade!

## Understanding the Workflow

GUARD follows a structured workflow:

### 1. Pre-Checks Phase
- Validates cluster health before any changes
- Creates baseline metrics snapshot
- Fails fast if any issues detected

### 2. GitOps Phase
- Creates feature branch in GitLab
- Updates Flux HelmRelease configurations
- Creates merge request for human review
- **Human Gate**: You review and merge

### 3. Deployment Phase (Flux)
- Flux detects config changes
- Applies new Istio version to cluster
- Kubernetes rolls out new pods

### 4. Validation Phase
- Waits for soak period
- Queries post-upgrade metrics
- Compares with baseline
- Validates against thresholds

### 5. Completion/Rollback
- If validation passes: Mark as successful
- If validation fails: Automatically create rollback MR

## Next Steps

Now that you've completed your first upgrade, explore:

### Upgrade More Clusters

Define additional batches in your config:

```yaml
batches:
  - name: dev-wave-1
    description: Development clusters - wave 1
    clusters:
      - eks-dev-us-east-1-app1
      - eks-dev-us-east-1-app2

  - name: prod-wave-1
    description: Production - critical services
    clusters:
      - eks-prod-us-east-1-api
```

### Progressive Rollout Strategy

Follow this recommended order:

```bash
# 1. Test
guard run --batch test --target-version 1.20.0
guard monitor --batch test

# 2. Development (wave 1)
guard run --batch dev-wave-1 --target-version 1.20.0
guard monitor --batch dev-wave-1

# 3. Development (wave 2)
guard run --batch dev-wave-2 --target-version 1.20.0
guard monitor --batch dev-wave-2

# 4. Staging
guard run --batch staging --target-version 1.20.0
guard monitor --batch staging --soak-period 120  # Longer soak

# 5. Production (wave 1 - critical)
guard run --batch prod-wave-1 --target-version 1.20.0
guard monitor --batch prod-wave-1 --soak-period 120

# 6. Production (wave 2 - remaining)
guard run --batch prod-wave-2 --target-version 1.20.0
guard monitor --batch prod-wave-2 --soak-period 120
```

### Customize Configuration

Explore advanced options:

- **Custom validation thresholds**: Adjust sensitivity
- **LLM-powered analysis**: Enable AI failure investigation
- **Notifications**: Set up Slack/PagerDuty alerts
- **Batch ordering**: Define dependencies between batches

See [Configuration Guide](configuration.md) for details.

### Set Up Automation

Integrate with your CI/CD:

```yaml
# .gitlab-ci.yml
istio-upgrade:
  stage: upgrade
  script:
    - guard run --batch $BATCH --target-version $VERSION
    - guard monitor --batch $BATCH
  only:
    - schedules
  variables:
    BATCH: "test"
    VERSION: "1.20.0"
```

## Troubleshooting

### Pre-checks fail

```bash
# Get detailed error info
guard run --batch test --target-version 1.20.0 --verbose

# Check specific cluster
guard registry show eks-test-us-east-1

# Verify Kubernetes access
kubectl cluster-info
```

### GitLab MR creation fails

```bash
# Verify GitLab token
aws secretsmanager get-secret-value --secret-id guard/gitlab-token

# Test GitLab connectivity
curl -H "PRIVATE-TOKEN: your-token" https://gitlab.yourcompany.com/api/v4/user
```

### Validation fails

```bash
# Check Datadog metrics manually
# View logs
guard monitor --batch test --verbose

# Skip validation (for testing)
guard monitor --batch test --skip-validation
```

### Need to rollback

```bash
# Trigger manual rollback
guard rollback --batch test

# This creates a rollback MR - review and merge to revert
```

## Getting Help

- **Documentation**: [docs/](.)
- **Examples**: [docs/examples/](examples/)
- **Issues**: [GitHub Issues](https://github.com/adickinson72/guard/issues)
- **Slack**: #guard-support

## What's Next?

- Read the [Architecture Documentation](architecture.md) to understand how GUARD works
- Review [Testing Guide](testing.md) if you want to contribute
- Check [Examples](examples/) for advanced usage scenarios
- See [API Reference](api-reference.md) for Python API usage
