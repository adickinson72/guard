# Security Documentation

This document covers security considerations, best practices, and required IAM permissions for GUARD.

## Table of Contents

- [Overview](#overview)
- [Credential Management](#credential-management)
- [IAM Permissions](#iam-permissions)
- [Network Security](#network-security)
- [Audit and Compliance](#audit-and-compliance)
- [Security Best Practices](#security-best-practices)
- [Incident Response](#incident-response)

## Overview

GUARD operates with elevated privileges to manage Istio across multiple clusters. Security is paramount.

### Security Principles

1. **Least Privilege**: Minimal permissions for each component
2. **Defense in Depth**: Multiple layers of security controls
3. **Audit Everything**: Comprehensive logging of all operations
4. **Secrets Isolation**: No credentials in code or config files
5. **Zero Trust**: Verify every access, every time

## Credential Management

### DO:

✅ **Store all credentials in AWS Secrets Manager**
```bash
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --secret-string "glpat-xxxxxxxxxxxx"
```

✅ **Use IAM roles with temporary credentials**
```bash
aws sts assume-role \
    --role-arn arn:aws:iam::123456789:role/GUARD-EKSAccess \
    --role-session-name igu-session
```

✅ **Rotate credentials regularly**
- GitLab tokens: Every 90 days
- Datadog keys: Every 90 days
- IAM role credentials: Automatically rotated (STS temporary credentials)

✅ **Use separate credentials for each environment**
- Dev: `igu-dev/gitlab-token`
- Staging: `igu-staging/gitlab-token`
- Prod: `igu-prod/gitlab-token`

### DON'T:

❌ **Never commit credentials to Git**
```bash
# Add to .gitignore
.env
*.key
secrets.yaml
credentials.json
```

❌ **Never store credentials in configuration files**
```yaml
# BAD - Don't do this!
gitlab:
  token: glpat-12345  # ❌ NO!

# GOOD - Reference secret instead
gitlab:
  token_secret: guard/gitlab-token  # ✅ YES!
```

❌ **Never log credentials**
```python
# BAD
logger.info(f"Using token: {token}")  # ❌ NO!

# GOOD
logger.info("Using GitLab token from Secrets Manager")  # ✅ YES!
```

❌ **Never use long-lived credentials when temporary ones are available**

### Secrets Manager Schema

Store secrets with proper structure:

#### GitLab Token
```json
{
  "name": "guard/gitlab-token",
  "description": "GitLab personal access token for GUARD",
  "value": "glpat-xxxxxxxxxxxx"
}
```

#### Datadog Credentials
```json
{
  "name": "guard/datadog-credentials",
  "description": "Datadog API and App keys for GUARD",
  "value": {
    "api_key": "xxxxxxxxxxxxx",
    "app_key": "xxxxxxxxxxxxx"
  }
}
```

#### LLM API Key (Optional)
```json
{
  "name": "igu/llm-api-key",
  "description": "OpenAI/Anthropic API key for failure analysis",
  "value": "sk-xxxxxxxxxxxxx"
}
```

## IAM Permissions

### GUARD Service Role

Create an IAM role for GUARD with these policies:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/guard-cluster-registry",
        "arn:aws:dynamodb:*:*:table/guard-cluster-registry/index/*"
      ]
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:igu/*"
      ]
    },
    {
      "Sid": "EKSDescribeAccess",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:ListClusters"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AssumeClusterRoles",
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole"
      ],
      "Resource": [
        "arn:aws:iam::*:role/GUARD-EKSAccess"
      ]
    }
  ]
}
```

### Cluster Access Role

Create per-cluster IAM roles for EKS access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EKSFullAccess",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:ListClusters"
      ],
      "Resource": "arn:aws:eks:*:*:cluster/eks-prod-*"
    }
  ]
}
```

**Trust relationship:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789:role/GUARD-ServiceRole"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "igu-cluster-access"
        }
      }
    }
  ]
}
```

### Kubernetes RBAC

Grant GUARD service account read-only access:

```yaml
# igu-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: igu
  namespace: istio-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: igu-reader
rules:
  # Read pods and deployments
  - apiGroups: [""]
    resources: ["pods", "namespaces"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list"]

  # Read Istio resources
  - apiGroups: ["networking.istio.io"]
    resources: ["*"]
    verbs: ["get", "list"]

  # No write permissions (GitOps only!)
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: igu-reader-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: igu-reader
subjects:
  - kind: ServiceAccount
    name: igu
    namespace: istio-system
```

Apply to each cluster:
```bash
kubectl apply -f igu-rbac.yaml
```

Update `aws-auth` ConfigMap:
```bash
kubectl edit configmap aws-auth -n kube-system
```

```yaml
mapRoles: |
  - rolearn: arn:aws:iam::123456789:role/GUARD-EKSAccess
    username: igu
    groups:
      - system:masters  # Or create custom group with limited permissions
```

## Network Security

### GitLab Access

- Use HTTPS for all GitLab API calls
- Verify TLS certificates
- Use GitLab's IP allowlist if available

```python
# Verify TLS in GitLab client
gitlab_client = gitlab.Gitlab(
    url="https://gitlab.company.com",
    private_token=token,
    ssl_verify=True  # ✅ Always verify TLS
)
```

### Datadog Access

- Use Datadog's public endpoints or private link
- Verify API key scopes (limit to metrics read-only if possible)

### EKS Access

- Use private EKS endpoints where possible
- Access clusters via VPN or bastion host
- Enable EKS audit logging

```bash
# Enable EKS control plane logging
aws eks update-cluster-config \
    --name eks-prod-us-east-1 \
    --logging '{"clusterLogging":[{"types":["api","audit","authenticator"],"enabled":true}]}'
```

## Audit and Compliance

### Logging

GUARD logs all operations with structured JSON:

```json
{
  "timestamp": "2024-10-18T10:30:00Z",
  "level": "INFO",
  "event": "upgrade_initiated",
  "user": "arn:aws:iam::123456789:user/alice",
  "batch_id": "prod-wave-1",
  "target_version": "1.20.0",
  "clusters": ["eks-prod-us-east-1-api", "eks-prod-us-east-1-web"],
  "request_id": "abc-123-def-456"
}
```

### CloudWatch Integration

Send logs to CloudWatch:

```yaml
# config.yaml
logging:
  level: INFO
  format: json
  output: cloudwatch
  cloudwatch:
    log_group: /aws/igu/production
    stream_name: igu-{hostname}-{pid}
```

### CloudTrail

Enable CloudTrail for AWS API calls:

```bash
aws cloudtrail create-trail \
    --name igu-audit-trail \
    --s3-bucket-name igu-audit-logs \
    --include-global-service-events

aws cloudtrail start-logging --name igu-audit-trail
```

Monitor for:
- `AssumeRole` calls
- `GetSecretValue` calls
- DynamoDB operations
- EKS cluster access

### GitLab Audit Events

Enable GitLab audit events for:
- MR creation
- MR approval
- Branch creation
- Commit activity

### Compliance Requirements

**SOC 2 / ISO 27001:**
- ✅ All operations logged
- ✅ Credentials encrypted at rest (Secrets Manager)
- ✅ Credentials encrypted in transit (TLS)
- ✅ Access control with IAM
- ✅ Audit trail in CloudTrail

**GDPR:**
- ✅ No PII stored
- ✅ Logs retained per policy
- ✅ Right to delete (purge logs)

## Security Best Practices

### 1. Principle of Least Privilege

```yaml
# Good: Separate roles per environment
production:
  role: arn:aws:iam::123:role/GUARD-Prod-EKSAccess

development:
  role: arn:aws:iam::123:role/GUARD-Dev-EKSAccess

# Bad: Single role with access to everything
```

### 2. Credential Rotation

```bash
# Automate credential rotation
# scripts/rotate-credentials.sh

# Rotate GitLab token
NEW_TOKEN=$(gitlab-api create-token --expires-in 90d)
aws secretsmanager update-secret \
    --secret-id guard/gitlab-token \
    --secret-string "$NEW_TOKEN"

# Rotate Datadog keys
# ... similar process
```

### 3. MFA for Production

Require MFA for production operations:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RequireMFAForProd",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/GUARD-Prod-*",
      "Condition": {
        "Bool": {
          "aws:MultiFactorAuthPresent": "true"
        }
      }
    }
  ]
}
```

### 4. IP Allowlisting

Restrict access to known IPs:

```json
{
  "Condition": {
    "IpAddress": {
      "aws:SourceIp": [
        "10.0.0.0/8",      # Corporate network
        "192.168.1.0/24"   # VPN
      ]
    }
  }
}
```

### 5. Session Limits

Use short-lived sessions:

```python
# Assume role with 1-hour session
credentials = sts.assume_role(
    RoleArn="arn:aws:iam::123:role/GUARD-EKSAccess",
    RoleSessionName="igu-session",
    DurationSeconds=3600  # 1 hour
)
```

### 6. Secrets Encryption

Use KMS for additional encryption:

```bash
# Create KMS key for GUARD secrets
aws kms create-key --description "GUARD Secrets Encryption Key"

# Create secret with KMS encryption
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --secret-string "glpat-xxx" \
    --kms-key-id arn:aws:kms:us-east-1:123:key/abc-123
```

### 7. Network Isolation

Run GUARD in private subnet:

```
┌─────────────────────────────────────────┐
│  VPC                                     │
│  ┌───────────────────────────────────┐  │
│  │  Private Subnet                   │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  GUARD EC2 Instance/Lambda    │  │  │
│  │  └─────────────────────────────┘  │  │
│  │         │                          │  │
│  │         ├─→ VPC Endpoint (Secrets)│  │
│  │         ├─→ VPC Endpoint (DynamoDB)│ │
│  │         └─→ NAT Gateway (GitLab)  │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Incident Response

### Security Incident Playbook

#### 1. Credential Compromise

**If GitLab token compromised:**

```bash
# Immediately revoke token
gitlab-api revoke-token --token-id 123

# Rotate to new token
NEW_TOKEN=$(gitlab-api create-token --expires-in 90d)
aws secretsmanager update-secret \
    --secret-id guard/gitlab-token \
    --secret-string "$NEW_TOKEN"

# Audit all MRs created with old token
gitlab-api list-mrs --created-by guard --since "2024-10-01"

# Review for unauthorized changes
```

**If AWS credentials compromised:**

```bash
# Immediately deny all access
aws iam attach-role-policy \
    --role-name GUARD-ServiceRole \
    --policy-arn arn:aws:iam::aws:policy/DenyAll

# Investigate using CloudTrail
aws cloudtrail lookup-events \
    --lookup-attributes AttributeKey=Username,AttributeValue=GUARD-ServiceRole \
    --start-time "2024-10-18T00:00:00Z"

# Create new role with fresh credentials
# Update GUARD configuration
# Remove deny policy
```

#### 2. Unauthorized Cluster Access

```bash
# Review CloudTrail for unusual activity
aws cloudtrail lookup-events \
    --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole

# Check EKS audit logs
kubectl logs -n kube-system -l component=kube-apiserver | grep igu

# Revoke cluster access
kubectl delete clusterrolebinding igu-reader-binding
```

#### 3. Data Breach

```bash
# Identify scope
aws dynamodb query \
    --table-name guard-cluster-registry \
    --select COUNT

# Notify security team
# Follow organization's data breach procedures
# Preserve logs for forensics
```

### Monitoring and Alerts

Set up CloudWatch alarms:

```bash
# Alert on failed authentication
aws cloudwatch put-metric-alarm \
    --alarm-name igu-auth-failures \
    --metric-name FailedAuthCount \
    --threshold 5 \
    --comparison-operator GreaterThanThreshold

# Alert on unusual API activity
aws cloudwatch put-metric-alarm \
    --alarm-name igu-high-api-calls \
    --metric-name APICallCount \
    --threshold 1000 \
    --comparison-operator GreaterThanThreshold
```

## Security Checklist

Before deploying GUARD:

- [ ] All credentials stored in AWS Secrets Manager
- [ ] IAM roles configured with least privilege
- [ ] MFA enabled for production access
- [ ] CloudTrail enabled and logging
- [ ] EKS audit logging enabled
- [ ] Kubernetes RBAC configured (read-only)
- [ ] Network security groups configured
- [ ] VPC endpoints configured for AWS services
- [ ] Credential rotation policy defined
- [ ] Incident response playbook documented
- [ ] Security monitoring and alerts configured
- [ ] Regular security audits scheduled

## Reporting Security Issues

**DO NOT** open public GitHub issues for security vulnerabilities.

Instead:
1. Email security@yourcompany.com
2. Use PGP key: [link to public key]
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 24 hours.
