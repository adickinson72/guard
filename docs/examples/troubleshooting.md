# Troubleshooting Guide

Common issues and solutions when using GUARD.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Configuration Issues](#configuration-issues)
- [AWS/DynamoDB Issues](#awsdynamodb-issues)
- [GitLab Issues](#gitlab-issues)
- [Datadog Issues](#datadog-issues)
- [Kubernetes/EKS Issues](#kuberneteseks-issues)
- [Pre-Check Failures](#pre-check-failures)
- [Validation Failures](#validation-failures)
- [Rollback Issues](#rollback-issues)
- [Performance Issues](#performance-issues)

## Installation Issues

### Issue: `pip install guard` fails

**Symptoms:**
```bash
$ pip install guard
ERROR: Could not find a version that satisfies the requirement guard
```

**Solutions:**

1. **Check Python version:**
```bash
python --version  # Must be 3.11+

# If too old, install newer Python
# macOS:
brew install python@3.11

# Ubuntu:
sudo apt install python3.11
```

2. **Upgrade pip:**
```bash
pip install --upgrade pip
pip install guard
```

3. **Install from source:**
```bash
git clone https://github.com/adickinson72/guard.git
cd guard
pip install -e .
```

### Issue: Import errors after installation

**Symptoms:**
```bash
$ guard --version
ModuleNotFoundError: No module named 'guard'
```

**Solutions:**

1. **Check installation:**
```bash
pip list | grep guard
# If not listed, reinstall
pip install guard
```

2. **Check Python path:**
```bash
which python
which pip
# Ensure they're from the same environment
```

3. **Use virtual environment:**
```bash
python -m venv venv
source venv/bin/activate
pip install guard
```

## Configuration Issues

### Issue: Config file not found

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: Configuration file not found: /home/user/.guard/config.yaml
```

**Solutions:**

1. **Create config directory:**
```bash
mkdir -p ~/.guard
```

2. **Copy example config:**
```bash
cp examples/config.yaml.example ~/.guard/config.yaml
```

3. **Specify config path:**
```bash
guard run --config /path/to/config.yaml --batch test --target-version 1.20.0
```

### Issue: Invalid configuration

**Symptoms:**
```bash
$ guard validate
Error: Invalid configuration: 1 validation error for GuardConfig
aws
  field required (type=value_error.missing)
```

**Solutions:**

1. **Validate YAML syntax:**
```bash
python -c "import yaml; yaml.safe_load(open('~/.guard/config.yaml'))"
```

2. **Check required fields:**
```yaml
# Minimum required config
aws:
  region: us-east-1
gitlab:
  url: https://gitlab.company.com
```

3. **Use validation command:**
```bash
guard validate --config ~/.guard/config.yaml --verbose
```

## AWS/DynamoDB Issues

### Issue: AWS credentials not found

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: Unable to locate credentials
```

**Solutions:**

1. **Configure AWS CLI:**
```bash
aws configure
# Enter: Access Key ID, Secret Access Key, Region, Output format
```

2. **Use environment variables:**
```bash
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_REGION=us-east-1
```

3. **Use AWS profile:**
```bash
export AWS_PROFILE=guard-dev
# Or in config:
aws:
  profile: guard-dev
```

### Issue: DynamoDB table not accessible

**Symptoms:**
```bash
$ guard list
Error: An error occurred (ResourceNotFoundException) when calling the Query operation:
Requested resource not found: Table: guard-cluster-registry not found
```

**Solutions:**

1. **Verify table exists:**
```bash
aws dynamodb describe-table --table-name guard-cluster-registry
```

2. **Create table if missing:**
```bash
./scripts/setup-dynamodb.sh
# Or manually:
aws dynamodb create-table \
    --table-name guard-cluster-registry \
    --attribute-definitions AttributeName=cluster_id,AttributeType=S \
    --key-schema AttributeName=cluster_id,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
```

3. **Check IAM permissions:**
```bash
# Ensure your IAM user/role has:
# - dynamodb:GetItem
# - dynamodb:Query
# - dynamodb:PutItem
# - dynamodb:UpdateItem
```

### Issue: Cannot assume role for cluster access

**Symptoms:**
```bash
$ guard run --batch prod --target-version 1.20.0
Error: An error occurred (AccessDenied) when calling the AssumeRole operation:
User is not authorized to perform: sts:AssumeRole
```

**Solutions:**

1. **Check trust relationship:**
```json
// Role's trust policy must allow your IAM user/role
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::123456789:user/your-user"
    },
    "Action": "sts:AssumeRole"
  }]
}
```

2. **Verify IAM permissions:**
```bash
aws sts assume-role \
    --role-arn arn:aws:iam::123456789:role/GUARD-EKSAccess \
    --role-session-name test
```

## GitLab Issues

### Issue: GitLab authentication fails

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: GitLab authentication failed: 401 Unauthorized
```

**Solutions:**

1. **Verify token in Secrets Manager:**
```bash
aws secretsmanager get-secret-value --secret-id guard/gitlab-token
```

2. **Check token validity:**
```bash
TOKEN=$(aws secretsmanager get-secret-value --secret-id guard/gitlab-token --query SecretString --output text)
curl -H "PRIVATE-TOKEN: $TOKEN" https://gitlab.company.com/api/v4/user
```

3. **Regenerate token:**
   - Go to GitLab → Settings → Access Tokens
   - Create new token with `api` and `write_repository` scopes
   - Update secret:
```bash
aws secretsmanager update-secret \
    --secret-id guard/gitlab-token \
    --secret-string "glpat-xxxxxxxxxxxx"
```

### Issue: Cannot create merge request

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: 403 Forbidden: You don't have permission to create merge requests
```

**Solutions:**

1. **Check repository access:**
   - Ensure you have at least Developer role in the GitLab project
   - Verify project path is correct in cluster registry

2. **Check token scopes:**
   - Token must have `api` scope for MR creation
   - Token must have `write_repository` scope for branch creation

3. **Test manually:**
```bash
# Get token
TOKEN=$(aws secretsmanager get-secret-value --secret-id guard/gitlab-token --query SecretString --output text)

# Test MR creation permission
curl -X POST -H "PRIVATE-TOKEN: $TOKEN" \
  "https://gitlab.company.com/api/v4/projects/YOUR_PROJECT_ID/merge_requests" \
  -d "source_branch=test-branch&target_branch=main&title=Test"
```

## Datadog Issues

### Issue: Datadog authentication fails

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: Datadog API error: 403 Forbidden
```

**Solutions:**

1. **Verify credentials:**
```bash
aws secretsmanager get-secret-value --secret-id guard/datadog-credentials
# Should return: {"api_key":"xxx","app_key":"xxx"}
```

2. **Test Datadog API:**
```bash
# Get credentials
CREDS=$(aws secretsmanager get-secret-value --secret-id guard/datadog-credentials --query SecretString --output text)
API_KEY=$(echo $CREDS | jq -r .api_key)
APP_KEY=$(echo $CREDS | jq -r .app_key)

# Test API
curl -X GET "https://api.datadoghq.com/api/v1/validate" \
  -H "DD-API-KEY: $API_KEY" \
  -H "DD-APPLICATION-KEY: $APP_KEY"
```

3. **Check API key scopes:**
   - API key must have metrics read permission
   - App key must be valid and not expired

### Issue: Datadog query returns no data

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Warning: No Datadog metrics found for cluster eks-test
```

**Solutions:**

1. **Verify tags exist:**
```bash
# Check if cluster has expected tags in Datadog
# Go to Datadog → Infrastructure → Host Map
# Verify tags match those in cluster registry
```

2. **Test query manually:**
```bash
# Use Datadog web UI → Metrics Explorer
# Or API:
curl -X GET "https://api.datadoghq.com/api/v1/query?query=avg:kubernetes.cpu.usage{cluster_name:eks-test}" \
  -H "DD-API-KEY: $API_KEY" \
  -H "DD-APPLICATION-KEY: $APP_KEY"
```

3. **Adjust query template:**
```yaml
# ~/.guard/config.yaml
datadog:
  queries:
    # Use correct tag names for your environment
    proxy_cpu: "avg:kubernetes.cpu.usage.total{kube_container_name:istio-proxy,cluster_name:{cluster_name}}"
```

## Kubernetes/EKS Issues

### Issue: Cannot connect to EKS cluster

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: Unable to connect to the server: dial tcp: lookup xxx.eks.amazonaws.com: no such host
```

**Solutions:**

1. **Update kubeconfig:**
```bash
aws eks update-kubeconfig \
    --name eks-test-us-east-1 \
    --region us-east-1 \
    --role-arn arn:aws:iam::123456789:role/GUARD-EKSAccess
```

2. **Test connectivity:**
```bash
kubectl cluster-info
kubectl get nodes
```

3. **Check VPC/network:**
   - Ensure you can reach EKS API endpoint
   - Check security groups
   - Verify VPN/bastion access if using private endpoint

### Issue: istioctl not found

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
Error: istioctl command not found
```

**Solutions:**

1. **Install istioctl:**
```bash
# Download and install
curl -L https://istio.io/downloadIstio | sh -
cd istio-*
export PATH=$PWD/bin:$PATH

# Verify
istioctl version
```

2. **Add to PATH:**
```bash
echo 'export PATH=$PATH:/path/to/istio/bin' >> ~/.bashrc
source ~/.bashrc
```

## Pre-Check Failures

### Issue: Kubernetes health check fails

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
✗ Cluster eks-test: Kubernetes health check failed
  Error: Unable to reach API server
```

**Solutions:**

1. **Verify cluster access:**
```bash
kubectl get nodes
kubectl get pods -n istio-system
```

2. **Check node status:**
```bash
kubectl get nodes
# All nodes should be Ready
# If NotReady, investigate node issues
```

3. **Check API server:**
```bash
kubectl cluster-info
# Should show API server URL and status
```

### Issue: Istio health check fails

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
✗ Cluster eks-test: Istio health check failed
  Error: istioctl analyze found 3 issues
```

**Solutions:**

1. **Run istioctl analyze manually:**
```bash
istioctl analyze -n istio-system

# Example output:
# Warn [IST0102] (Namespace default) The namespace is not enabled for Istio injection.
#   Suggestion: Run 'kubectl label namespace default istio-injection=enabled' to enable it
```

2. **Fix identified issues:**
```bash
# Follow istioctl suggestions
kubectl label namespace default istio-injection=enabled
```

3. **Skip non-critical warnings:**
```yaml
# ~/.guard/config.yaml
pre_checks:
  istio_analyze:
    ignore_warnings: true  # Only fail on errors
```

### Issue: Active Datadog alerts

**Symptoms:**
```bash
$ guard run --batch test --target-version 1.20.0
✗ Cluster eks-test: Active Datadog alerts detected
  Alerts:
    - High error rate on API service (CRITICAL)
```

**Solutions:**

1. **Investigate alerts:**
   - Go to Datadog → Monitors
   - Check alert details
   - Resolve underlying issue

2. **Wait for alerts to clear:**
```bash
# Re-run pre-checks after fixing issues
guard run --batch test --target-version 1.20.0
```

3. **Override if false positive:**
```bash
# Only if you're certain the alert is safe to ignore
guard run --batch test --target-version 1.20.0 --ignore-alerts
```

## Validation Failures

### Issue: Latency threshold exceeded

**Symptoms:**
```bash
$ guard monitor --batch test
✗ Validation failed: Latency increased 15% (threshold: 10%)
  Baseline P95: 200ms
  Current P95: 230ms
```

**Solutions:**

1. **Investigate latency increase:**
```bash
# Check Datadog dashboards
# Look for:
# - Service dependency changes
# - Resource constraints
# - Network issues
```

2. **Adjust threshold if acceptable:**
```yaml
# ~/.guard/config.yaml
validation:
  thresholds:
    latency_increase_percent: 20  # Increase if 15% is acceptable
```

3. **Rollback if problematic:**
```bash
guard rollback --batch test
```

### Issue: Error rate threshold exceeded

**Symptoms:**
```bash
$ guard monitor --batch test
✗ Validation failed: Error rate 0.15% exceeds threshold 0.1%
```

**Solutions:**

1. **Check error logs:**
```bash
kubectl logs -n istio-system -l app=istiod --tail=100
kubectl logs -n istio-system -l app=istio-ingressgateway --tail=100
```

2. **Check for known issues:**
   - Review Istio release notes for target version
   - Check for breaking changes
   - Look for configuration incompatibilities

3. **Rollback:**
```bash
guard rollback --batch test
```

### Issue: Flux not syncing

**Symptoms:**
```bash
$ guard monitor --batch test
Waiting for Flux sync...
Error: Flux sync timeout after 15 minutes
```

**Solutions:**

1. **Check Flux logs:**
```bash
kubectl logs -n flux-system -l app=source-controller
kubectl logs -n flux-system -l app=helm-controller
```

2. **Check Flux resources:**
```bash
kubectl get helmrelease -n istio-system
kubectl describe helmrelease istio -n istio-system
```

3. **Manual sync:**
```bash
flux reconcile source git flux-system
flux reconcile helmrelease istio -n istio-system
```

## Rollback Issues

### Issue: Rollback MR not created

**Symptoms:**
```bash
$ guard rollback --batch test
Error: Failed to create rollback MR: 500 Internal Server Error
```

**Solutions:**

1. **Check GitLab connectivity:**
```bash
curl https://gitlab.company.com
```

2. **Verify GitLab token:**
```bash
aws secretsmanager get-secret-value --secret-id guard/gitlab-token
```

3. **Manual rollback:**
```bash
# Manually revert Flux config in GitLab
# Change version back to previous in HelmRelease YAML
# Commit and push
```

## Performance Issues

### Issue: Pre-checks taking too long

**Symptoms:**
```bash
$ guard run --batch large-batch --target-version 1.20.0
# Hangs for 30+ minutes
```

**Solutions:**

1. **Enable parallel execution:**
```yaml
# ~/.guard/config.yaml
execution:
  max_parallel_clusters: 5  # Check multiple clusters in parallel
```

2. **Reduce batch size:**
```yaml
# Split large batches into smaller ones
batches:
  - name: large-batch-1
    clusters: [cluster1, cluster2, cluster3]
  - name: large-batch-2
    clusters: [cluster4, cluster5, cluster6]
```

3. **Optimize Datadog queries:**
```yaml
# Reduce query time range
datadog:
  query_time_range_minutes: 60  # Default: 120
```

### Issue: Out of memory errors

**Symptoms:**
```bash
$ guard run --batch large-batch --target-version 1.20.0
Error: MemoryError: Unable to allocate array
```

**Solutions:**

1. **Increase memory:**
```bash
# If running in container/lambda
# Increase memory allocation

# If running locally
# Close other applications
```

2. **Process in smaller batches:**
```bash
# Instead of one large batch
# Split into multiple smaller batches
```

## Getting Help

If you're still stuck:

1. **Enable verbose logging:**
```bash
guard run --batch test --target-version 1.20.0 --verbose
```

2. **Check logs:**
```bash
# Application logs
tail -f ~/.guard/logs/guard.log

# System logs
journalctl -u guard -f
```

3. **Collect diagnostic info:**
```bash
guard diagnose --batch test --output diagnostic-report.json
# Share this report when asking for help
```

4. **Open an issue:**
   - [GitHub Issues](https://github.com/adickinson72/guard/issues)
   - Include diagnostic report
   - Include error messages
   - Include steps to reproduce

5. **Community support:**
   - Slack: #guard-support
   - [GitHub Discussions](https://github.com/adickinson72/guard/discussions)
