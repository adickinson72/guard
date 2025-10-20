# Kubernetes Deployment Guide

This guide covers deploying GUARD inside a Kubernetes cluster using EKS Pod Identity for secure cross-account access.

## Overview

Running GUARD inside an EKS pod provides several benefits:

- **Secure Authentication**: Uses EKS Pod Identity (IRSA) to assume roles across multiple AWS accounts
- **Network Access**: Direct access to EKS API servers from within the cluster
- **Automation**: Enables scheduled upgrades via CronJob
- **Scalability**: Better suited for managing 75+ clusters

## Prerequisites

- EKS cluster with OIDC provider configured
- IAM role with cross-account assume role permissions
- Container registry for storing GUARD Docker image
- `kubectl` configured for your management cluster

## Architecture

IGu runs in a dedicated `igu-system` namespace with:

- **ServiceAccount**: Annotated with IAM role ARN for Pod Identity
- **Deployment**: Long-running pod for manual execution
- **CronJob**: Optional scheduled upgrade automation
- **RBAC**: ClusterRole with permissions to restart workloads

## Quick Start

### 1. Build and Push Docker Image

```bash
# Build the Docker image
docker build -t <YOUR_REGISTRY>/igu:latest .

# Push to container registry
docker push <YOUR_REGISTRY>/igu:latest
```

### 2. Configure IAM Role

Create an IAM role with the following trust policy:

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
          "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:sub": "system:serviceaccount:igu-system:igu",
          "oidc.eks.<REGION>.amazonaws.com/id/<OIDC_ID>:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

Attach policies to allow:
- EKS cluster access (`eks:DescribeCluster`, `eks:ListClusters`)
- STS assume role to other accounts
- Any other required permissions (DynamoDB, Secrets Manager, etc.)

### 3. Update Kubernetes Manifests

Edit `k8s/serviceaccount.yaml` and replace `<ACCOUNT_ID>` with your AWS account ID:

```yaml
metadata:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/GUARD-CrossAccountRole
```

Edit `k8s/deployment.yaml` and `k8s/cronjob.yaml` to replace `<YOUR_REGISTRY>` with your container registry.

### 4. Deploy to Kubernetes

Using kubectl:

```bash
# Apply all manifests
kubectl apply -f k8s/
```

Or using Kustomize:

```bash
# Deploy using kustomize
kubectl apply -k k8s/
```

### 5. Verify Deployment

```bash
# Check namespace
kubectl get ns igu-system

# Check pods
kubectl get pods -n igu-system

# Check service account
kubectl get sa -n igu-system igu -o yaml

# Verify RBAC
kubectl get clusterrole igu-manager
kubectl get clusterrolebinding igu-manager-binding
```

## Usage

### Manual Execution

Execute GUARD commands from within the running pod:

```bash
# Get shell access to the pod
kubectl exec -it -n igu-system deploy/igu -- /bin/bash

# Run GUARD commands
igu run --batch dev-wave-1 --target-version 1.20.0
igu status --cluster prod-us-east-1
```

Or execute directly without shell:

```bash
kubectl exec -n igu-system deploy/igu -- igu run --batch dev-wave-1 --target-version 1.20.0
```

### Scheduled Execution (CronJob)

The CronJob manifest (`k8s/cronjob.yaml`) is configured to run weekly on Sunday at 2 AM UTC.

To customize the schedule, edit the `spec.schedule` field using cron syntax:

```yaml
spec:
  # Daily at 2 AM
  schedule: "0 2 * * *"

  # Every Monday at 3 AM
  schedule: "0 3 * * 1"
```

To trigger a manual run from the CronJob:

```bash
kubectl create job -n igu-system manual-upgrade --from=cronjob/igu-scheduled-upgrade
```

### View Logs

```bash
# Deployment logs
kubectl logs -n igu-system deploy/igu -f

# CronJob logs (latest job)
kubectl logs -n igu-system job/igu-scheduled-upgrade-<timestamp> -f

# List all jobs
kubectl get jobs -n igu-system
```

## Configuration

### ConfigMap

Store GUARD configuration in the ConfigMap (`k8s/configmap.yaml`):

```yaml
data:
  config.yaml: |
    clusters:
      - cluster_id: "prod-us-east-1"
        batch_id: "prod-wave-1"
        environment: "production"
        region: "us-east-1"
        # ... other configuration
```

After updating, apply the changes:

```bash
kubectl apply -f k8s/configmap.yaml

# Restart deployment to pick up new config
kubectl rollout restart -n igu-system deployment/igu
```

### Environment Variables

Additional environment variables can be added to the Deployment or CronJob manifests:

```yaml
env:
- name: AWS_REGION
  value: us-east-1
- name: LOG_LEVEL
  value: DEBUG
- name: DRY_RUN
  value: "true"
```

## Pod Restart Functionality

GUARD now includes automatic pod restart functionality for Istio sidecars after upgrades.

### How It Works

After a successful Istio control plane upgrade:

1. GUARD queries for namespaces with the `istio-injection=enabled` label
2. For each namespace, it identifies all Deployments, StatefulSets, and DaemonSets
3. Restarts each workload using a rolling restart strategy (adds `kubectl.kubernetes.io/restartedAt` annotation)
4. Kubernetes performs a rolling update, replacing pods with new sidecar versions

### Configuration

The restart functionality is enabled by default. To disable:

```python
from igu.validation.engine import ValidationEngine

# Disable pod restart
engine = ValidationEngine(
    soak_period_minutes=60,
    restart_pods_with_sidecars=False
)
```

### Usage

```python
from igu.clients.kubernetes_client import KubernetesClient
from igu.validation.engine import ValidationEngine

# Initialize clients
k8s_client = KubernetesClient(context="my-cluster")
validation_engine = ValidationEngine()

# Restart all pods with sidecars in all namespaces
result = validation_engine.restart_pods_with_istio_sidecars(k8s_client)

# Restart pods in a specific namespace only
result = validation_engine.restart_pods_with_istio_sidecars(
    k8s_client,
    namespace="my-namespace"
)

# Check result
if result.passed:
    print(f"Success: {result.message}")
else:
    print(f"Failed: {result.message}")
```

### RBAC Requirements

The pod restart functionality requires the following permissions (already included in `k8s/rbac.yaml`):

```yaml
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "daemonsets"]
  verbs: ["get", "list", "watch", "patch"]
```

## Troubleshooting

### Pod Identity Issues

If the pod cannot assume the IAM role:

```bash
# Check service account annotation
kubectl get sa -n igu-system igu -o jsonpath='{.metadata.annotations}'

# Verify environment variables in pod
kubectl exec -n igu-system deploy/igu -- env | grep AWS

# Test AWS credentials
kubectl exec -n igu-system deploy/igu -- aws sts get-caller-identity
```

### Permission Errors

If GUARD cannot restart workloads:

```bash
# Verify RBAC is applied
kubectl get clusterrole igu-manager
kubectl get clusterrolebinding igu-manager-binding

# Check what permissions the service account has
kubectl auth can-i patch deployments --as=system:serviceaccount:igu-system:igu -n default
```

### Image Pull Errors

If pods fail to pull the image:

```bash
# Check pod events
kubectl describe pod -n igu-system <pod-name>

# Verify image exists
docker pull <YOUR_REGISTRY>/igu:latest

# If using private registry, create imagePullSecret
kubectl create secret docker-registry regcred \
  --docker-server=<YOUR_REGISTRY> \
  --docker-username=<USERNAME> \
  --docker-password=<PASSWORD> \
  -n igu-system

# Add to deployment.yaml
spec:
  imagePullSecrets:
  - name: regcred
```

## Security Considerations

1. **Least Privilege**: The IAM role should only have permissions required for GUARD operations
2. **Network Policies**: Consider adding NetworkPolicy to restrict pod network access
3. **Pod Security Standards**: The manifests follow restricted pod security standards:
   - Runs as non-root user (UID 1000)
   - Drops all capabilities
   - No privilege escalation
4. **Secret Management**: Use AWS Secrets Manager or Kubernetes Secrets for sensitive data
5. **Image Scanning**: Scan Docker images for vulnerabilities before deployment

## Multi-Cluster Deployment

To manage multiple EKS clusters, deploy GUARD in a central "management" cluster:

1. Configure the management cluster's IAM role to assume roles in all target clusters
2. Store kubeconfig contexts for all clusters in a ConfigMap or Secret
3. Use the appropriate context when initializing KubernetesClient:

```python
# Connect to different clusters
for cluster in clusters:
    k8s_client = KubernetesClient(context=cluster.context_name)
    # Perform operations
```

## Uninstalling

To remove GUARD from your cluster:

```bash
# Delete all resources
kubectl delete -k k8s/

# Or individually
kubectl delete -f k8s/
```

## Additional Resources

- [EKS Pod Identity Documentation](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kustomize Documentation](https://kustomize.io/)
