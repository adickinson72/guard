# Kubernetes Manifests for GUARD

This directory contains Kubernetes manifests for deploying GUARD inside an EKS cluster.

## Files

- **namespace.yaml**: Creates the `guard-system` namespace
- **serviceaccount.yaml**: ServiceAccount with EKS Pod Identity annotation
- **rbac.yaml**: ClusterRole and ClusterRoleBinding for GUARD permissions
- **configmap.yaml**: ConfigMap for GUARD configuration (customize as needed)
- **deployment.yaml**: Deployment for long-running GUARD pod
- **cronjob.yaml**: CronJob for scheduled Istio upgrades
- **kustomization.yaml**: Kustomize configuration for managing all resources

## Quick Deploy

### Prerequisites

1. Update `serviceaccount.yaml` with your AWS account ID
2. Update `deployment.yaml` and `cronjob.yaml` with your container registry
3. Build and push the Docker image (see root Dockerfile)

### Using kubectl

```bash
kubectl apply -f .
```

### Using Kustomize

```bash
kubectl apply -k .
```

## Customization

### Update IAM Role

Edit `serviceaccount.yaml`:

```yaml
eks.amazonaws.com/role-arn: arn:aws:iam::YOUR_ACCOUNT_ID:role/YOUR_ROLE_NAME
```

### Update Container Image

Edit `deployment.yaml` and `cronjob.yaml`:

```yaml
image: your-registry.com/guard:v1.0.0
```

Or update `kustomization.yaml`:

```yaml
images:
- name: <YOUR_REGISTRY>/guard
  newName: your-registry.com/guard
  newTag: v1.0.0
```

### Update CronJob Schedule

Edit `cronjob.yaml`:

```yaml
spec:
  schedule: "0 2 * * 0"  # Weekly on Sunday at 2 AM
```

### Add Configuration

Edit `configmap.yaml` and add your GUARD configuration:

```yaml
data:
  config.yaml: |
    clusters:
      - cluster_id: "prod-us-east-1"
        # ... your configuration
```

## Verification

```bash
# Check all resources
kubectl get all -n guard-system

# Check service account
kubectl get sa -n guard-system guard -o yaml

# Check RBAC
kubectl get clusterrole guard-manager
kubectl get clusterrolebinding guard-manager-binding

# View logs
kubectl logs -n guard-system deploy/guard
```

## Documentation

See [docs/kubernetes-deployment.md](../docs/kubernetes-deployment.md) for complete documentation.
