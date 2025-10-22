# Kubernetes Deployment Checklist

Before deploying GUARD to your production EKS cluster, complete the following steps:

## Prerequisites

- [ ] EKS cluster with OIDC provider configured
- [ ] Container registry access (ECR, Docker Hub, etc.)
- [ ] AWS IAM permissions to create roles and policies
- [ ] kubectl configured with cluster admin access
- [ ] Docker installed for image building

## Step 1: Build and Push Docker Image

```bash
# Build the image
docker build -t <YOUR_REGISTRY>/guard:v0.2.0 .

# Example for AWS ECR:
# aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
# docker tag guard:v0.2.0 <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/guard:v0.2.0
# docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/guard:v0.2.0
```

## Step 2: Set Up AWS IAM Role for Pod Identity

### Create IAM Role

Create an IAM role with the following trust policy (replace placeholders):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:sub": "system:serviceaccount:guard-system:guard",
          "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

### Attach IAM Policies

The role needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:ListClusters"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole"
      ],
      "Resource": "arn:aws:iam::*:role/GUARD-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/guard-cluster-registry",
        "arn:aws:dynamodb:*:*:table/guard-cluster-registry/index/*",
        "arn:aws:dynamodb:*:*:table/guard-locks"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:*:*:secret:guard/*"
      ]
    }
  ]
}
```

## Step 3: Create AWS Secrets

```bash
# GitLab token
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --secret-string "glpat-xxxxxxxxxxxx" \
    --region us-east-1

# Datadog credentials
aws secretsmanager create-secret \
    --name guard/datadog-credentials \
    --secret-string '{"api_key":"xxxxx","app_key":"xxxxx"}' \
    --region us-east-1
```

## Step 4: Set Up DynamoDB Tables

```bash
# Run the setup script
./scripts/setup-dynamodb.sh guard-cluster-registry us-east-1

# Create locks table
aws dynamodb create-table \
    --table-name guard-locks \
    --attribute-definitions AttributeName=resource_id,AttributeType=S \
    --key-schema AttributeName=resource_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region us-east-1
```

## Step 5: Update Kubernetes Manifests

### Update `k8s/serviceaccount.yaml`

Replace `<ACCOUNT_ID>` with your AWS account ID:

```yaml
eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/GUARD-CrossAccountRole
```

### Update `k8s/deployment.yaml` and `k8s/cronjob.yaml`

Replace `<YOUR_REGISTRY>` with your container registry:

```yaml
image: <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/guard:v0.2.0
```

Or use Kustomize to set images globally in `k8s/kustomization.yaml`:

```yaml
images:
- name: <YOUR_REGISTRY>/guard
  newName: <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/guard
  newTag: v0.2.0
```

### Update `k8s/configmap.yaml`

Edit the ConfigMap to set your specific values:

```yaml
data:
  config.yaml: |
    aws:
      region: us-east-1  # Your AWS region
    gitlab:
      url: https://gitlab.yourcompany.com  # Your GitLab URL
    # ... other settings
```

## Step 6: Deploy to Kubernetes

```bash
# Using kubectl
kubectl apply -f k8s/

# Or using Kustomize
kubectl apply -k k8s/

# Verify deployment
kubectl get all -n guard-system
kubectl get sa -n guard-system guard -o yaml
kubectl logs -n guard-system deploy/guard
```

## Step 7: Verify Installation

```bash
# Test AWS credentials
kubectl exec -n guard-system deploy/guard -- aws sts get-caller-identity

# Run validation
kubectl exec -n guard-system deploy/guard -- guard validate

# Test listing clusters (should show empty initially)
kubectl exec -n guard-system deploy/guard -- guard list
```

## Step 8: Populate Cluster Registry

Add your clusters to the DynamoDB registry. Example Python script:

```python
from guard.registry.cluster_registry import ClusterRegistry
from guard.core.models import ClusterConfig

registry = ClusterRegistry(table_name="guard-cluster-registry", region="us-east-1")

cluster = ClusterConfig(
    cluster_id="prod-us-east-1-api",
    batch_id="prod-wave-1",
    environment="production",
    region="us-east-1",
    aws_role_arn="arn:aws:iam::123456789012:role/EKS-ClusterAccess",
    current_istio_version="1.19.0",
    flux_path="clusters/prod/us-east-1/api/istio.yaml",
    gitlab_project_id="infrastructure/k8s-fleet",
)

registry.put_cluster(cluster)
```

## Placeholders Reference

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `<ACCOUNT_ID>` | AWS Account ID | `123456789012` |
| `<REGION>` | AWS Region | `us-east-1` |
| `<OIDC_ID>` | EKS OIDC Provider ID | `EXAMPLED539D4633E53DE1B71EXAMPLE` |
| `<YOUR_REGISTRY>` | Container registry URL | `123456789012.dkr.ecr.us-east-1.amazonaws.com` |

## Troubleshooting

### Pod fails to start
- Check image pull permissions
- Verify IAM role annotation on ServiceAccount
- Check logs: `kubectl logs -n guard-system deploy/guard`

### Cannot assume roles
- Verify OIDC provider configuration
- Check IAM trust policy
- Test: `kubectl exec -n guard-system deploy/guard -- aws sts get-caller-identity`

### ConfigMap not loaded
- Verify ConfigMap exists: `kubectl get cm -n guard-system`
- Check mount: `kubectl exec -n guard-system deploy/guard -- cat /app/config/config.yaml`

## Production Recommendations

- [ ] Use specific image tags (not `latest`)
- [ ] Enable Pod Disruption Budgets
- [ ] Set up monitoring and alerting for GUARD itself
- [ ] Use NetworkPolicy to restrict pod network access
- [ ] Regularly rotate AWS credentials
- [ ] Review and audit IAM permissions quarterly
- [ ] Enable audit logging for all GUARD operations
- [ ] Test rollback procedures in staging first

## Next Steps

After successful deployment:

1. Run a test upgrade on a non-production cluster
2. Review MR creation in GitLab
3. Test validation and rollback workflows
4. Set up automated schedules via CronJob
5. Configure Datadog monitors for GUARD operations
