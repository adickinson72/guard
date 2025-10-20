# Configuration Guide

This guide covers all configuration options for GUARD (GitOps Upgrade Automation with Rollback Detection).

## Table of Contents

- [Configuration File Location](#configuration-file-location)
- [Configuration File Format](#configuration-file-format)
- [AWS Settings](#aws-settings)
- [GitLab Settings](#gitlab-settings)
- [Datadog Settings](#datadog-settings)
- [Validation Settings](#validation-settings)
- [Rollback Settings](#rollback-settings)
- [LLM Settings](#llm-settings)
- [Batch Configuration](#batch-configuration)
- [Logging Configuration](#logging-configuration)
- [Cluster Registry](#cluster-registry)

## Configuration File Location

GUARD looks for configuration in the following locations (in order):

1. Path specified via `--config` CLI flag
2. `~/.guard/config.yaml`
3. `/etc/igu/config.yaml`

## Configuration File Format

GUARD uses YAML format for configuration. See `examples/config.yaml.example` for a complete example.

## AWS Settings

```yaml
aws:
  region: us-east-1              # Default AWS region
  profile: default               # Optional: AWS profile to use

  dynamodb:
    table_name: guard-cluster-registry  # DynamoDB table for cluster registry
    region: us-east-1                  # Region for DynamoDB table

  secrets_manager:
    gitlab_token_secret: guard/gitlab-token                    # Secret name for GitLab token
    datadog_credentials_secret: guard/datadog-credentials      # Secret name for Datadog credentials
```

### Required IAM Permissions

The IAM role/user running GUARD needs the following permissions:

**DynamoDB:**
- `dynamodb:GetItem`
- `dynamodb:PutItem`
- `dynamodb:Query`
- `dynamodb:Scan`
- `dynamodb:UpdateItem`

**Secrets Manager:**
- `secretsmanager:GetSecretValue`

**EKS:**
- `eks:DescribeCluster`

**STS:**
- `sts:AssumeRole` (for cross-account cluster access)

## GitLab Settings

```yaml
gitlab:
  url: https://gitlab.company.com      # GitLab instance URL
  default_target_branch: main          # Default branch for MRs
```

### GitLab Token

Store your GitLab personal access token in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --secret-string "glpat-xxxxxxxxxxxx"
```

Required token scopes:
- `api` - Full API access
- `write_repository` - Create branches and commits

## Datadog Settings

```yaml
datadog:
  site: datadoghq.com              # Datadog site (e.g., datadoghq.com, datadoghq.eu)

  # Optional: Customize Datadog queries
  queries:
    control_plane_errors: "sum:istio.pilot.xds.push.errors{cluster:{cluster_name}}.as_count()"
    error_rate: "sum:trace.http.request.errors{service:*,env:{environment}}.as_count() / sum:trace.http.request.hits{service:*,env:{environment}}.as_count()"
    latency_p95: "avg:trace.http.request.duration.by.service.95p{env:{environment}}"
    latency_p99: "avg:trace.http.request.duration.by.service.99p{env:{environment}}"
    proxy_cpu: "avg:kubernetes.cpu.usage.total{kube_container_name:istio-proxy,cluster_name:{cluster_name}}"
    proxy_memory: "avg:kubernetes.memory.usage{kube_container_name:istio-proxy,cluster_name:{cluster_name}}"
```

### Datadog Credentials

Store Datadog API and App keys in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name guard/datadog-credentials \
    --secret-string '{"api_key":"your-api-key","app_key":"your-app-key"}'
```

## Validation Settings

```yaml
validation:
  soak_period_minutes: 60              # How long to wait after upgrade before validation
  flux_sync_timeout_minutes: 15        # Maximum time to wait for Flux to sync

  thresholds:
    latency_increase_percent: 10       # Maximum allowed latency increase (%)
    error_rate_max: 0.001              # Maximum allowed error rate (0.1%)
    resource_increase_percent: 50      # Maximum allowed resource usage increase (%)
```

### Threshold Details

- **latency_increase_percent**: If p95 latency increases more than this percentage compared to pre-upgrade baseline, validation fails
- **error_rate_max**: Absolute error rate threshold (e.g., 0.001 = 0.1%)
- **resource_increase_percent**: If CPU/memory usage increases more than this percentage, validation fails

## Rollback Settings

```yaml
rollback:
  auto_create_mr: true                # Automatically create rollback MR on failure
  require_manual_approval: true        # Require manual approval for rollback MR

  notification:
    enabled: true
    webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## LLM Settings

Optional AI-powered failure analysis:

```yaml
llm:
  enabled: false                      # Enable LLM-powered analysis
  provider: openai                    # LLM provider (openai, anthropic)
  model: gpt-4                        # Model to use
  api_key_secret: igu/llm-api-key     # Secret name for API key
```

Store LLM API key in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
    --name igu/llm-api-key \
    --secret-string "sk-xxxxxxxx"
```

## Batch Configuration

Batches define groups of clusters to upgrade together:

```yaml
batches:
  - name: test
    description: Test cluster
    clusters:
      - eks-test-us-east-1

  - name: dev-wave-1
    description: Development clusters - first wave
    clusters:
      - eks-dev-us-east-1-app1
      - eks-dev-us-east-1-app2

  - name: prod-wave-1
    description: Production - Critical services
    clusters:
      - eks-prod-us-east-1-api
      - eks-prod-us-east-1-web
```

### Batch Ordering

You can define batch prerequisites to enforce ordering:

```yaml
batch_order:
  dev-wave-1:
    - test                           # dev-wave-1 requires test to complete
  prod-wave-1:
    - staging                        # prod-wave-1 requires staging to complete
```

## Logging Configuration

```yaml
logging:
  level: INFO                         # Log level (DEBUG, INFO, WARNING, ERROR)
  format: json                        # Log format (json, text)
  output: stdout                      # Output destination (stdout, file)
```

## Cluster Registry

The cluster registry is stored in DynamoDB and contains metadata for each cluster.

### Registry Schema

Each cluster entry contains:

```json
{
  "cluster_id": "eks-prod-us-east-1-app1",
  "batch_id": "prod-wave-1",
  "environment": "production",
  "region": "us-east-1",
  "gitlab_repo": "infra/k8s-clusters",
  "flux_config_path": "clusters/prod/us-east-1/app1/istio-helmrelease.yaml",
  "aws_role_arn": "arn:aws:iam::123456789:role/GUARD-EKSAccess",
  "current_istio_version": "1.19.3",
  "datadog_tags": {
    "cluster": "eks-prod-us-east-1-app1",
    "service": "istio-system",
    "env": "production"
  },
  "owner_team": "platform-engineering",
  "owner_handle": "@platform-team",
  "status": "healthy"
}
```

### Populating the Registry

1. Create DynamoDB table:

```bash
./scripts/setup-dynamodb.sh
```

2. Import cluster data:

```bash
# From JSON file
guard registry import --file clusters.json

# Add single cluster
guard registry add --cluster-id eks-prod-us-east-1-app1 \
    --batch-id prod-wave-1 \
    --environment production \
    --region us-east-1 \
    --gitlab-repo infra/k8s-clusters \
    --flux-config-path clusters/prod/us-east-1/app1/istio-helmrelease.yaml
```

3. Verify registry:

```bash
# List all clusters
guard registry list

# List clusters by batch
guard registry list --batch prod-wave-1

# Show cluster details
guard registry show eks-prod-us-east-1-app1
```

## Environment Variables

GUARD also supports configuration via environment variables:

- `GUARD_CONFIG_PATH` - Path to config file
- `AWS_PROFILE` - AWS profile to use
- `AWS_REGION` - AWS region
- `GUARD_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)
- `GUARD_DRY_RUN` - Enable dry-run mode (true/false)

## Validation

Validate your configuration file:

```bash
guard validate --config ~/.guard/config.yaml
```

This checks:
- YAML syntax
- Required fields
- Secret availability
- DynamoDB table accessibility
- GitLab connectivity
- Datadog API access

## Best Practices

1. **Store sensitive data in AWS Secrets Manager**, never in config files
2. **Use different batches** for different environments and risk levels
3. **Start with conservative thresholds** and adjust based on experience
4. **Enable notifications** for production batches
5. **Use longer soak periods** for production (120+ minutes)
6. **Test configuration** with `guard validate` before running upgrades
7. **Keep config in version control** (excluding secrets)
8. **Use IAM roles** instead of long-lived credentials
9. **Enable audit logging** for compliance requirements
10. **Document batch ordering** and dependencies clearly
