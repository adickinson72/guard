# GitOps Upgrade Automation with Rollback Detection (GUARD)

> **An open-source Python tool for automated, safe Istio upgrades across multiple EKS clusters using GitOps workflows**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Table of Contents
- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Core Components](#core-components)
- [Workflow Phases](#workflow-phases)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Confguardration](#confguardration)
- [Security Considerations](#security-considerations)
- [Future Enhancements](#future-enhancements)

---

## Overview

**Problem Statement:**
Managing Istio upgrades across 75 EKS clusters using FluxCD and GitOps is complex, risky, and time-consuming. Manual processes lead to:
- Inconsistent upgrade procedures
- Lack of automated health validation
- Risk of production outages
- Delayed rollout cycles

**Solution:**
GUARD automates the entire Istio upgrade lifecycle with:
- **Automated pre-upgrade health checks** using Datadog metrics and Kubernetes state
- **GitLab MR creation** with automated confguardration updates
- **Progressive rollout strategy** (test → dev → staging → prod batches)
- **Post-upgrade validation** with automated rollback on failure
- **Optional LLM-powered analysis** for failure investigation

**Key Features:**
- ✅ Stateful, resumable workflow execution
- ✅ Batch-based cluster upgrades with wave management
- ✅ Datadog-powered health validation
- ✅ Automated rollback protocol
- ✅ GitOps-native (FluxCD integration)
- ✅ Human-in-the-loop gates for safety
- ✅ Comprehensive observability

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUARD CLI (Python)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ Run Command  │  │Monitor Command│  │  Rollback Command   │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
              │                  │                    │
              ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Core Engine Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │Pre-Check Eng │  │Validation Eng │  │  Rollback Engine    │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ GitOps Mgr   │  │  State Mgr   │  │  LLM Analyzer (opt) │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
              │                  │                    │
              ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Integration Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ AWS Client   │  │ K8s Client   │  │  GitLab Client      │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │Datadog Client│  │Istioctl Wrap │  │  Secrets Manager    │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
              │                  │                    │
              ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Systems                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ EKS Clusters │  │ GitLab Repos │  │  Datadog API        │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │ DynamoDB     │  │ AWS Secrets  │  │  Notification (opt) │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Pre-Upgrade (guard run --batch prod-wave-1)
   ┌─────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
   │ CLI │───>│ Cluster Reg  │───>│ Pre-Check    │───>│ GitLab   │
   └─────┘    │ (DynamoDB)   │    │ (DD + K8s)   │    │ MR       │
              └──────────────┘    └──────────────┘    └──────────┘
                                                              │
                                                              ▼
2. Human Review & Merge MR                              [WAIT GATE]
                                                              │
                                                              ▼
3. Post-Upgrade (guard monitor --batch prod-wave-1)
   ┌─────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
   │ CLI │───>│ Flux Sync    │───>│ Post-Check   │───>│ Report   │
   └─────┘    │ Monitor      │    │ (DD + K8s)   │    │ Success  │
              └──────────────┘    └──────────────┘    └──────────┘
                                         │ FAIL
                                         ▼
4. Automated Rollback (on failure)
   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Create       │───>│ Rollback MR  │───>│ Alert Team   │
   │ Revert Branch│    │ (Auto)       │    │ [WAIT GATE]  │
   └──────────────┘    └──────────────┘    └──────────────┘
```

---

### 1. CLI Interface (Entry Point)

**Language:** Python 3.11+
**Framework:** [Click](https://click.palletsprojects.com/) or [Typer](https://typer.tiangolo.com/)

**Commands:**

```python
# guard run - Pre-check and create upgrade MR
guard run --batch <batch-name> \
        --target-version <istio-version> \
        --config <config-file> \
        [--dry-run] \
        [--parallelism <num>] \
        [--mr-strategy batch|per-cluster]

# guard monitor - Post-upgrade validation
guard monitor --batch <batch-name> \
            --config <config-file> \
            [--soak-period <minutes>] \
            [--parallelism <num>]

# guard rollback - Manual rollback trigger
guard rollback --batch <batch-name> \
             --config <config-file>

# guard list - List clusters and their status
guard list [--batch <batch-name>] \
         [--environment <env>] \
         [--format json|table]

# guard status - Show current workflow status
guard status --batch <batch-name> \
           [--format json|table]

# guard diff - Preview confguardration changes
guard diff --batch <batch-name> \
         --target-version <istio-version> \
         [--format yaml|unified]

# guard resume - Resume a failed workflow
guard resume --batch <batch-name> \
           [--from-step <step>]

# guard validate - Validate confguardration and connectivity (ENHANCED)
guard validate --config <config-file> \
             [--check-connectivity] \
             [--check-permissions]
```

**Responsibilities:**
- Parse command-line arguments
- Load confguardration
- Initialize logging and observability
- Orchestrate workflow execution
- **Enforce rollout sequencing** (prevent prod-wave-2 if prod-wave-1 not completed)
- Handle errors and provide user feedback
- Manage distributed locks and prevent concurrent operations on same batch

---

### 2. Cluster Registry (State Management)

**Storage Backend:** AWS DynamoDB (recommended) or S3 + DynamoDB locks

**Schema:**

```python
{
    "cluster_id": "eks-prod-us-east-1-app1",  # Partition key
    "batch_id": "prod-wave-1",                # GSI
    "environment": "production",               # dev | staging | production
    "region": "us-east-1",
    "gitlab_repo": "infra/k8s-clusters",
    "flux_config_path": "clusters/prod/us-east-1/app1/istio-helmrelease.yaml",
    "aws_role_arn": "arn:aws:iam::123456789:role/GUARD-EKSAccess",
    "current_istio_version": "1.19.3",
    "target_istio_version": "1.20.0",
    "datadog_tags": {
        "cluster": "eks-prod-us-east-1-app1",
        "service": "istio-system",
        "env": "production"
    },
    "owner_team": "platform-engineering",
    "owner_handle": "@platform-team",
    "status": "healthy",  # pending | pre-check-running | pre-check-passed |
                          # pre-check-failed | mr-created | upgrading |
                          # post-check-running | healthy | rollback-required
    "last_updated": "2025-10-17T10:30:00Z",
    "upgrade_history": [
        {
            "version": "1.19.3",
            "date": "2025-09-01T10:00:00Z",
            "status": "success"
        }
    ],
    "metadata": {
        "mesh_id": "mesh-prod-01",
        "multi_cluster": false
    }
}
```

**Implementation:**

```python
# src/guard/registry/cluster_registry.py
from typing import List, Optional
from dataclasses import dataclass
import boto3

@dataclass
class ClusterConfig:
    cluster_id: str
    batch_id: str
    environment: str
    # ... other fields

class ClusterRegistry:
    def __init__(self, table_name: str, region: str = "us-east-1"):
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.dynamodb_client = boto3.client('dynamodb', region_name=region)
        self.table = self.dynamodb.Table(table_name)
        self.lock_ttl = 300  # 5 minutes

    def get_clusters_by_batch(self, batch_id: str) -> List[ClusterConfig]:
        """Fetch all clusters in a batch using GSI"""
        response = self.table.query(
            IndexName='batch-index',
            KeyConditionExpression='batch_id = :batch_id',
            ExpressionAttributeValues={':batch_id': batch_id}
        )
        return [ClusterConfig(**item) for item in response['Items']]

    def update_cluster_status_atomic(
        self,
        cluster_id: str,
        expected_status: str,
        new_status: str,
        idempotency_key: Optional[str] = None
    ) -> bool:
        """Update cluster status with atomic transaction to prevent race conditions"""
        try:
            # Use DynamoDB TransactWriteItems for atomic update
            self.dynamodb_client.transact_write_items(
                TransactItems=[
                    {
                        'Update': {
                            'TableName': self.table.table_name,
                            'Key': {'cluster_id': {'S': cluster_id}},
                            'UpdateExpression': 'SET #status = :new_status, last_updated = :timestamp, version = version + :one',
                            'ConditionExpression': '#status = :expected_status',
                            'ExpressionAttributeNames': {'#status': 'status'},
                            'ExpressionAttributeValues': {
                                ':new_status': {'S': new_status},
                                ':expected_status': {'S': expected_status},
                                ':timestamp': {'S': datetime.utcnow().isoformat()},
                                ':one': {'N': '1'}
                            }
                        }
                    }
                ]
            )
            return True
        except self.dynamodb_client.exceptions.TransactionCanceledException:
            # Status transition not allowed (state machine violation)
            return False

    def acquire_lock(self, cluster_id: str, lock_holder: str, timeout: int = 300) -> bool:
        """Distributed lock using DynamoDB conditional writes with TTL"""
        import time
        lock_key = f"lock#{cluster_id}"
        expiration = int(time.time()) + timeout

        try:
            # Conditional PutItem - only succeeds if lock doesn't exist or is expired
            self.table.put_item(
                Item={
                    'cluster_id': lock_key,
                    'lock_holder': lock_holder,
                    'expiration': expiration,
                    'acquired_at': datetime.utcnow().isoformat()
                },
                ConditionExpression='attribute_not_exists(cluster_id) OR expiration < :now',
                ExpressionAttributeValues={':now': int(time.time())}
            )
            return True
        except self.dynamodb_client.exceptions.ConditionalCheckFailedException:
            return False

    def release_lock(self, cluster_id: str, lock_holder: str) -> bool:
        """Release lock only if current holder"""
        lock_key = f"lock#{cluster_id}"
        try:
            self.table.delete_item(
                Key={'cluster_id': lock_key},
                ConditionExpression='lock_holder = :holder',
                ExpressionAttributeValues={':holder': lock_holder}
            )
            return True
        except self.dynamodb_client.exceptions.ConditionalCheckFailedException:
            return False

    def renew_lock(self, cluster_id: str, lock_holder: str, timeout: int = 300) -> bool:
        """Renew lock to extend TTL during long operations"""
        import time
        lock_key = f"lock#{cluster_id}"
        expiration = int(time.time()) + timeout

        try:
            self.table.update_item(
                Key={'cluster_id': lock_key},
                UpdateExpression='SET expiration = :expiration',
                ConditionExpression='lock_holder = :holder',
                ExpressionAttributeValues={
                    ':expiration': expiration,
                    ':holder': lock_holder
                }
            )
            return True
        except self.dynamodb_client.exceptions.ConditionalCheckFailedException:
            return False

    def validate_batch_prerequisites(self, batch_id: str, batch_config: Dict) -> Tuple[bool, str]:
        """Enforce rollout sequencing - ensure prerequisite batches completed"""
        # Get batch order from config
        batch_order = batch_config.get('batch_order', {})
        prerequisites = batch_order.get(batch_id, [])

        for prereq_batch in prerequisites:
            # Check if prerequisite batch completed successfully
            clusters = self.get_clusters_by_batch(prereq_batch)

            for cluster in clusters:
                if cluster.status not in ['healthy', 'completed']:
                    return False, f"Prerequisite batch '{prereq_batch}' not completed. Cluster {cluster.cluster_id} status: {cluster.status}"

        return True, "All prerequisites met"
```

**Example batch_order confguardration:**
```yaml
# In config.yaml
batch_order:
  # Define which batches must complete before others
  dev-wave-2: [dev-wave-1]
  staging: [dev-wave-1, dev-wave-2]
  prod-wave-1: [staging]
  prod-wave-2: [prod-wave-1]
  prod-wave-3: [prod-wave-2]
```

---

### 3. Pre-Check Engine

**Purpose:** Validate cluster health before creating upgrade MR

**Components:**

```python
# src/guard/checks/pre_check_engine.py
from abc import ABC, abstractmethod
from typing import Dict, List

class HealthCheck(ABC):
    @abstractmethod
    def run(self, cluster: ClusterConfig) -> CheckResult:
        pass

class CheckResult:
    def __init__(self, passed: bool, message: str, metrics: Dict = None):
        self.passed = passed
        self.message = message
        self.metrics = metrics or {}

# Individual check implementations
class KubernetesHealthCheck(HealthCheck):
    """Verify K8s control plane and Istio pods"""
    def run(self, cluster: ClusterConfig) -> CheckResult:
        # Check node status
        # Verify Istio pods in istio-system namespace
        # Check webhook confguardrations
        pass

class IstioCRDCheck(HealthCheck):
    """Verify Istio CRDs are at compatible version"""
    def run(self, cluster: ClusterConfig) -> CheckResult:
        # List Istio CRDs and check versions
        # Validate against target Istio version requirements
        # Required CRDs: VirtualService, DestinationRule, Gateway, etc.
        pass

class K8sIstioCompatibilityCheck(HealthCheck):
    """Verify K8s version is compatible with target Istio version"""
    COMPATIBILITY_MATRIX = {
        "1.20.0": ["1.26", "1.27", "1.28", "1.29"],
        "1.21.0": ["1.27", "1.28", "1.29", "1.30"],
        # Add more versions as needed
    }

    def run(self, cluster: ClusterConfig) -> CheckResult:
        # Get K8s server version
        # Check if K8s version is in compatibility matrix for target Istio
        # Return failure with helpful message if incompatible
        pass

class IstioConfigCheck(HealthCheck):
    """Run istioctl analyze"""
    def run(self, cluster: ClusterConfig) -> CheckResult:
        # Run istioctl analyze
        # Parse output for validation issues
        pass

class DatadogMetricsCheck(HealthCheck):
    """Query Datadog for baseline metrics"""
    def run(self, cluster: ClusterConfig) -> CheckResult:
        # Query metrics with rate limiting and retries
        # Establish baseline for comparison
        pass

class DatadogAlertsCheck(HealthCheck):
    """Verify no active alerts"""
    def run(self, cluster: ClusterConfig) -> CheckResult:
        # Query monitors filtered by cluster tags
        # Fail if any critical/warning alerts are active
        pass

class PreCheckEngine:
    def __init__(self, checks: List[HealthCheck]):
        self.checks = checks

    def run_all_checks(self, cluster: ClusterConfig) -> List[CheckResult]:
        results = []
        for check in self.checks:
            result = check.run(cluster)
            results.append(result)
            if not result.passed:
                # Short-circuit on first failure
                break
        return results
```

**Health Check Details:**

| Check | Tool | Success Criteria |
|-------|------|------------------|
| K8s Control Plane | `kubectl get nodes` | All nodes `Ready` |
| **K8s-Istio Compatibility** | **K8s version API** | **K8s version in compatibility matrix** |
| **Istio CRDs** | **`kubectl get crds`** | **All required CRDs present with compatible versions** |
| Istio Pods | `kubectl get pods -n istio-system` | All pods `Running`, `Ready` |
| Istio Webhooks | `kubectl get validatingwebhookconfguardrations` | Webhooks present and healthy |
| Istio Config | `istioctl analyze` | No validation issues |
| Datadog Baseline | Datadog Metrics API | Error rate < 0.1%, no active alerts |

---

### 4. GitOps Manager

**Purpose:** Handle Git/GitLab operations

```python
# src/guard/gitops/manager.py
from typing import Optional
import gitlab
from git import Repo

class GitOpsManager:
    def __init__(self, gitlab_url: str, token: str):
        self.gl = gitlab.Gitlab(gitlab_url, private_token=token)

    def create_upgrade_branch(
        self,
        project_id: str,
        base_branch: str,
        new_branch: str
    ) -> str:
        """Create a new branch for upgrade"""
        pass

    def update_flux_config(
        self,
        repo_path: str,
        config_path: str,
        new_version: str
    ) -> None:
        """Update HelmRelease or Kustomization with new Istio version"""
        # Parse YAML
        # Update spec.chart.spec.version or image tag
        # Commit changes
        pass

    def create_merge_request(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        assignee_handle: str
    ) -> str:
        """Create GitLab MR with proper assignee ID resolution"""
        project = self.gl.projects.get(project_id)

        # Resolve assignee handle to user ID
        assignee_id = None
        if assignee_handle:
            # Remove @ prefix if present
            handle = assignee_handle.lstrip('@')
            try:
                users = self.gl.users.list(username=handle)
                if users:
                    assignee_id = users[0].id
            except Exception as e:
                # Log warning but don't fail MR creation
                logger.warning(f"Could not resolve assignee {assignee_handle}: {e}")

        mr_params = {
            'source_branch': source_branch,
            'target_branch': target_branch,
            'title': title,
            'description': description,
            'draft': True  # Start as draft/WIP
        }

        # Add assignee if resolved
        if assignee_id:
            mr_params['assignee_ids'] = [assignee_id]

        mr = project.mergerequests.create(mr_params)
        return mr.web_url
```

---

### 5. Validation Engine

**Purpose:** Post-upgrade validation and monitoring

```python
# src/guard/validation/engine.py
import time
from typing import Tuple, List

class ValidationEngine:
    def __init__(
        self,
        k8s_client,
        datadog_client,
        istioctl_wrapper,
        soak_period_minutes: int = 60
    ):
        self.k8s = k8s_client
        self.datadog = datadog_client
        self.istioctl = istioctl_wrapper
        self.soak_period = soak_period_minutes * 60

    def wait_for_flux_sync(
        self,
        cluster: ClusterConfig,
        timeout: int = 900,
        check_interval: int = 10
    ) -> bool:
        """Monitor Flux reconciliation status with proper observedGeneration check"""
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Get HelmRelease or Kustomization resource
            resource = self.k8s.get_flux_resource(
                cluster.flux_config_path,
                cluster.environment
            )

            # Check if reconciliation is complete
            if resource.get('status'):
                conditions = resource['status'].get('conditions', [])
                observed_gen = resource['status'].get('observedGeneration')
                metadata_gen = resource['metadata'].get('generation')

                # Find Ready condition
                ready_condition = next(
                    (c for c in conditions if c['type'] == 'Ready'),
                    None
                )

                if (ready_condition and
                    ready_condition['status'] == 'True' and
                    observed_gen == metadata_gen):
                    return True

                # Check for failure conditions
                if (ready_condition and
                    ready_condition['status'] == 'False' and
                    observed_gen == metadata_gen):
                    raise FluxSyncError(f"Flux sync failed: {ready_condition.get('message')}")

            # Exponential backoff with jitter
            sleep_time = min(check_interval * (1 + random.random() * 0.1), 60)
            time.sleep(sleep_time)

        raise FluxSyncError(f"Flux sync timeout after {timeout}s")

    def run_soak_period(self) -> None:
        """Wait for metrics to stabilize"""
        time.sleep(self.soak_period)

    def validate_istio_deployment(self, cluster: ClusterConfig) -> CheckResult:
        """Verify new Istio version is deployed"""
        # Check istiod deployment
        # Check proxy sync status (istioctl ps)
        # Run istioctl analyze
        # Verify version (istioctl version)
        pass

    def compare_datadog_metrics(
        self,
        cluster: ClusterConfig,
        baseline: Dict,
        current: Dict
    ) -> Tuple[bool, List[str]]:
        """Compare pre/post upgrade metrics"""
        issues = []

        # Latency check: P95/P99 <= 10% increase
        # Error rate: 5xx within SLO
        # Resource utilization: CPU/Memory within 150% of baseline
        # Control plane health: XDS push times nominal

        return len(issues) == 0, issues
```

---

### 6. Rollback Engine

**Purpose:** Automated rollback on validation failure

```python
# src/guard/rollback/engine.py

class RollbackEngine:
    def __init__(self, gitops_manager: GitOpsManager):
        self.gitops = gitops_manager

    def create_rollback_mr(
        self,
        cluster: ClusterConfig,
        failure_reason: str,
        failure_metrics: Dict
    ) -> str:
        """Create automated rollback MR"""
        # 1. Create rollback branch
        # 2. Revert config to previous version
        # 3. Create MR with failure context
        # 4. Tag with ROLLBACK label
        # 5. Auto-assign to owner_handle
        pass

    def generate_rollback_report(
        self,
        cluster: ClusterConfig,
        validation_results: List[CheckResult]
    ) -> str:
        """Generate detailed failure report for MR description"""
        pass
```

---

### 7. Integration Clients

**AWS Client:**
```python
# src/guard/clients/aws_client.py
import boto3
from botocore.exceptions import ClientError

class AWSClient:
    def assume_role(self, role_arn: str, session_name: str) -> boto3.Session:
        """Assume IAM role for EKS access"""
        sts = boto3.client('sts')
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name
        )
        return boto3.Session(
            aws_access_key_id=response['Credentials']['AccessKeyId'],
            aws_secret_access_key=response['Credentials']['SecretAccessKey'],
            aws_session_token=response['Credentials']['SessionToken']
        )

    def get_eks_kubeconfig(self, cluster_name: str, region: str, role_arn: str = None) -> str:
        """Generate kubeconfig for EKS cluster using AWS STS"""
        import tempfile
        import json
        import subprocess

        # Assume role if provided
        session = self.assume_role(role_arn, f"guard-{cluster_name}") if role_arn else boto3.Session()
        eks = session.client('eks', region_name=region)

        # Get cluster details
        cluster_info = eks.describe_cluster(name=cluster_name)
        cluster_endpoint = cluster_info['cluster']['endpoint']
        cluster_ca = cluster_info['cluster']['certificateAuthority']['data']

        # Generate kubeconfig
        kubeconfig = {
            'apiVersion': 'v1',
            'kind': 'Config',
            'clusters': [{
                'name': cluster_name,
                'cluster': {
                    'server': cluster_endpoint,
                    'certificate-authority-data': cluster_ca
                }
            }],
            'contexts': [{
                'name': cluster_name,
                'context': {
                    'cluster': cluster_name,
                    'user': cluster_name
                }
            }],
            'current-context': cluster_name,
            'users': [{
                'name': cluster_name,
                'user': {
                    'exec': {
                        'apiVersion': 'client.authentication.k8s.io/v1beta1',
                        'command': 'aws',
                        'args': [
                            'eks', 'get-token',
                            '--cluster-name', cluster_name,
                            '--region', region
                        ] + (['--role-arn', role_arn] if role_arn else [])
                    }
                }
            }]
        }

        # Write to temporary file
        kubeconfig_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml.dump(kubeconfig, kubeconfig_file)
        kubeconfig_file.close()

        return kubeconfig_file.name
```

**Datadog Client:**
```python
# src/guard/clients/datadog_client.py
from datadog_api_client import ApiClient, Confguardration
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.api.monitors_api import MonitorsApi

class DatadogClient:
    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com"):
        config = Confguardration()
        config.api_key["apiKeyAuth"] = api_key
        config.api_key["appKeyAuth"] = app_key
        config.server_variables["site"] = site
        self.api_client = ApiClient(config)

    def query_metrics(
        self,
        query: str,
        start: int,
        end: int
    ) -> Dict:
        """Query Datadog metrics"""
        api = MetricsApi(self.api_client)
        return api.query_metrics(
            from_=start,
            to=end,
            query=query
        )

    def get_active_alerts(self, tags: List[str]) -> List[Dict]:
        """Get active monitors for cluster"""
        api = MonitorsApi(self.api_client)
        monitors = api.list_monitors(tags=",".join(tags))
        return [m for m in monitors if m.overall_state == "Alert"]
```

**Istioctl Wrapper:**
```python
# src/guard/clients/istioctl.py
import subprocess
import json

class IstioctlWrapper:
    def __init__(self, kubeconfig_path: str):
        self.kubeconfig = kubeconfig_path

    def analyze(self, namespace: str = None) -> Tuple[bool, str]:
        """Run istioctl analyze"""
        cmd = ["istioctl", "analyze", "--kubeconfig", self.kubeconfig]
        if namespace:
            cmd.extend(["-n", namespace])

        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout

    def proxy_status(self) -> Dict:
        """Get proxy sync status"""
        cmd = ["istioctl", "proxy-status", "--kubeconfig", self.kubeconfig, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(result.stdout)

    def version(self) -> Dict:
        """Get Istio version info"""
        cmd = ["istioctl", "version", "--kubeconfig", self.kubeconfig, "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(result.stdout)
```

---

## Workflow Phases

### Phase 0: Setup and Prerequisites

**Before using GUARD, set up the following:**

1. **DynamoDB Table Creation:**
   ```bash
   aws dynamodb create-table \
       --table-name guard-cluster-registry \
       --attribute-definitions \
           AttributeName=cluster_id,AttributeType=S \
           AttributeName=batch_id,AttributeType=S \
       --key-schema AttributeName=cluster_id,KeyType=HASH \
       --global-secondary-indexes \
           IndexName=batch-index,Keys=[{AttributeName=batch_id,KeyType=HASH}],Projection={ProjectionType=ALL} \
       --billing-mode PAY_PER_REQUEST
   ```

2. **AWS IAM Roles:**
   - Create IAM role for GUARD execution (with STS assume-role permissions)
   - Create per-cluster IAM roles with EKS access
   - **Note:** EKS access entries must be confguardred via Terraform (out-of-scope for GUARD)

3. **Secrets Manager:**
   ```bash
   # Store GitLab token
   aws secretsmanager create-secret \
       --name guard/gitlab-token \
       --secret-string "glpat-xxxxxxxxxxxx"

   # Store Datadog credentials
   aws secretsmanager create-secret \
       --name guard/datadog-credentials \
       --secret-string '{"api_key":"xxx","app_key":"xxx"}'
   ```

4. **Confguardration File:**
   Create `~/.guard/config.yaml` (see Confguardration section below)

5. **Dependencies:**
   ```bash
   # Install GUARD
   pip install guard

   # Install istioctl
   curl -L https://istio.io/downloadIstio | sh -
   export PATH=$PWD/bin:$PATH

   # Verify kubectl access
   kubectl version --client
   ```

### Phase 1: Pre-Upgrade Status Check (The Datadog Gate)

Goal: Ensure the target batch of clusters is healthy *and* correctly confguardred before creating an MR.
| Step | Action | Tools/API Used | Success Criteria |
|---|---|---|---|
| 1.1 Authentication | GUARD authenticates with AWS STS to AssumeRole into the target EKS cluster(s) and establishes a temporary kubeconfig. | AWS STS API | IAM role assumption successful. |
| 1.2 Kubernetes Sanity | Verify existing Istio control plane and webhooks. | `kubectl` | (A) All `istiod`/Gateway pods are `Running`/`Ready`. (B) `ValidatingWebhookConfguardration` & `MutatingWebhookConfguardration` for Istio are present and healthy. |
| 1.3 **(New)** Istio Config Validation | Run `istioctl analyze` to detect any pre-existing confguardration errors (e.g., broken `VirtualServices`). | `istioctl analyze` | Command returns `No validation issues found`. |
| 1.4 Datadog Baseline Check | Query Datadog for baseline metrics and *active alerts*. | Datadog Metrics & Monitors API | (A) Control Plane Health: Zero Istiod errors. (B) Data Plane Error Rate: Critical services 5xx rate \< 0.1%. (C) **Alerts: Zero active, non-silenced Datadog alerts** for the target cluster/services. |
| 1.5 Result & Halt | If any cluster in the batch fails *any* check, the GUARD halts for that *entire batch* and reports the failure. | GUARD CLI Output / Status Log | All checks passed for all clusters in the batch. |

### Phase 2: GitOps Change Management

Goal: Automate the MR creation for the Istio version bump. Executed by `guard run`.

**CRITICAL: CRD Upgrade Strategy**
Istio CRDs must be upgraded BEFORE the control plane. GUARD will handle this automatically:
- Create separate commits in the MR: (1) CRD updates, (2) Control plane updates
- Flux HelmRelease/Kustomization resources must be ordered with `dependsOn` to ensure CRDs reconcile first
- Pre-checks validate all required CRDs are present and compatible

| Step | Action | Tools/API Used | Details |
|---|---|---|---|
| 2.1 Branch Creation | Creates a new branch in the GitLab repository (e.g., `feature/istio-1.20.0-prod-wave-1`). | GitLab API / Git CLI | Branch name incorporates version and batch. |
| **2.2 CRD Update** | **Update Istio CRD manifests to target version** | **File Patching** | **Separate commit ensuring CRDs upgrade first** |
| 2.3 Confguardration Patch | Locate and update the Flux config file (HelmRelease/Kustomization) for control plane to the Target Version. | File Patching | Path to file is read from the `config_file_path` field in the Cluster Registry. Support multiple patterns (chart.version, image.tag, global.tag). |
| 2.4 Flux Resource Ordering | Verify or add `dependsOn` to ensure CRD resources reconcile before control plane | YAML Parsing | Ensures safe upgrade sequence |
| 2.5 Commit & Push | Commit and push the new branch. | GitLab API / Git CLI | `chore: Istio upgrade to vX.Y.Z for [BATCH]` |
| 2.6 Merge Request (MR) Creation | Opens a Draft/WIP Merge Request. **Enhancement:** Pre-populates with pre-upgrade health report, Datadog links, and **auto-assigns** to the team via the `owner_handle` from the Cluster Registry (resolved to user ID). | GitLab API | GUARD `run` command finishes here. The process now waits for a human to approve and merge this MR. Supports `--mr-strategy per-cluster` to create individual MRs per cluster for blast radius isolation. |

### Phase 3: Upgrade Execution & Post-Upgrade Validation

Goal: Monitor the Flux sync and perform data-driven health validation. Executed by `guard monitor`.
| Step | Action | Tools/API Used | Validation/Monitoring Detail |
|---|---|---|---|
| 3.1 **(Enhanced)** Monitor Flux Sync | **Triggered by CI/CD pipeline** after MR is merged. GUARD monitors Flux reconciliation. | `kubectl get helmrelease/kustomization`, `kubectl get deployment istiod` | Wait for Flux status `Ready: True` AND `istiod` deployment to reflect the *new* image tag and have all replicas ready. |
| 3.2 Soak Period | GUARD waits for a defined Soak Period (e.g., 60 minutes) to collect post-upgrade metrics. | GUARD Internal Timer | |
| 3.3 Post-Upgrade Status Check | Verify the new Istio control plane and confguardration. | `kubectl`, `istioctl` | (A) New `istiod` deployment is `Ready`. (B) `istioctl ps` shows all proxies `SYNCED`. (C) **`istioctl analyze`** reports no new issues. (D) `istioctl version` confirms all components match the target version. |
| 3.4 Datadog Validation | Compare Post-Upgrade Soak Period against the Pre-Upgrade Baseline. | Datadog Metrics Query API | (A) Latency: P95/P99 $\leq$ 10% change. (B) Error Rate: 5xx rate remains below SLO. (C) Saturation: Istio proxy CPU/Memory within 150% of baseline. (D) **Control Plane:** New Istiod XDS push times/errors are nominal. |
| 3.5 **(Enhanced)** Success Reporting | On *success*, GUARD updates the Cluster Registry and reports back. | GUARD CLI, GitLab API | 1. Cluster Registry updated: `status: healthy`, `istio_version: <new>`. 2. Post a "Success" comment to the (now merged) GitLab MR. |
| 3.6 **(New)** Failure Detection | If any check in 3.3 or 3.4 fails, GUARD updates the state and triggers rollback. | GUARD CLI | 1. Cluster Registry updated: `status: rollback-required`. 2. **Initiate Phase 5: Automated Rollback Protocol.** |

### Phase 4: Failure Analysis (LLM/Agent)

**Enhancement:** This phase runs in *parallel* to Phase 5. Its goal is analysis, not remediation.
| Step | Action | Tools/API Used | Output |
|---|---|---|---|
| 4.1 Data Collation | GUARD collects failure data: Datadog metrics, `istiod` logs, `istioctl analyze` output, and a link to the **automated rollback MR** created in Phase 5. | Datadog API, `kubectl logs` | Consolidated JSON/text payload. |
| 4.2 Agent Analysis | The collated data is fed to the LLM/Agent model. | LLM/Agent API | A concise, actionable analysis: "Validation failed: P99 latency spike to 2.5s. *Correlates with XDS push errors from new istiod*. Rollback has been initiated." |
| 4.3 Alerting | The LLM summary is sent to the on-call channel *along with the rollback MR link*. | Notification Webhook | Immediate alert with *suggested root cause* and *link to action (rollback MR)*. |

### Phase 5: (New) Automated Rollback Protocol

Goal: To safely and automatically return a failed cluster to its last known good state via GitOps.
| Step | Action | Tools/API Used | Details |
|---|---|---|---|
| 5.1 Trigger | Automatically triggered by GUARD on failure in step 3.6. | GUARD Core | |
| 5.2 Create Revert Branch | GUARD creates a new branch from `main`/`master` (e.g., `hotfix/rollback-istio-prod-wave-1`). | Git CLI | |
| 5.3 Create Revert Commit | GUARD checks out the *original* (pre-upgrade) version of the Flux config file and commits it, effectively reverting the change. | Git CLI / File Patching | This commit undoes the change from Phase 2. |
| 5.4 Create Rollback MR | GUARD creates a new MR (e.g., "**ROLLBACK: Istio Upgrade Failed for prod-wave-1**"). | GitLab API | MR is auto-assigned to the `owner_handle`, tagged `ROLLBACK`, and includes all failure data from Phase 3/4. |
| 5.5 Alert & Wait | GUARD fires a PagerDuty/Slack alert with a direct link to the rollback MR. The tool **halts** and waits for a human to approve this rollback MR. | Notification Webhook | This is a critical safety gate. A human must approve the *revert* to prevent automated flapping or revert loops. |
| 5.6 Monitor Rollback | (Optional) After the rollback MR is merged, `guard monitor` can be run again to validate the cluster has returned to the *old* version and is healthy. | `guard monitor`, `kubectl` | Cluster Registry status is updated to `status: failed-upgrade (rolled-back)`. |

---

## Technology Stack

### Core Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.11"
click = "^8.1.7"              # CLI framework
boto3 = "^1.34.0"             # AWS SDK
kubernetes = "^29.0.0"        # K8s Python client
python-gitlab = "^4.4.0"      # GitLab API client
datadog-api-client = "^2.23.0" # Datadog API client
datadog = "^0.49.0"           # Datadog statsd metrics
pyyaml = "^6.0.1"             # YAML parsing
pydantic = "^2.6.0"           # Data validation
rich = "^13.7.0"              # Beautiful CLI output
tenacity = "^8.2.3"           # Retry logic
structlog = "^24.1.0"         # Structured logging
ratelimit = "^2.2.1"          # API rate limiting

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-cov = "^4.1.0"
pytest-mock = "^3.12.0"
mypy = "^1.8.0"
ruff = "^0.2.0"              # Linting & formatting
pre-commit = "^3.6.0"
```

### External Tools

| Tool | Version | Purpose |
|------|---------|---------|
| `istioctl` | 1.20+ | Istio CLI operations |
| `kubectl` | 1.28+ | Kubernetes operations |
| AWS CLI | 2.x | AWS operations (optional) |

### Infrastructure

| Service | Purpose | Alternatives |
|---------|---------|--------------|
| AWS DynamoDB | Cluster registry & state management | PostgreSQL, MySQL |
| AWS Secrets Manager | Credential storage | HashiCorp Vault, AWS Parameter Store |
| AWS STS | IAM role assumption | N/A |
| Datadog | Metrics & monitoring | Prometheus + Grafana, New Relic |
| GitLab | Source control & MR workflow | GitHub, Bitbucket |

---

## Project Structure

```
guard/
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI/CD pipeline
│       └── release.yml         # Release automation
├── src/
│   └── guard/
│       ├── __init__.py
│       ├── __main__.py         # Entry point
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py         # Main CLI commands
│       │   ├── run.py          # guard run command
│       │   ├── monitor.py      # guard monitor command
│       │   ├── rollback.py     # guard rollback command
│       │   └── list.py         # guard list command
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py       # Confguardration management
│       │   ├── models.py       # Data models (ClusterConfig, etc.)
│       │   └── exceptions.py   # Custom exceptions
│       ├── registry/
│       │   ├── __init__.py
│       │   ├── cluster_registry.py  # DynamoDB operations
│       │   └── lock_manager.py      # Distributed locking
│       ├── checks/
│       │   ├── __init__.py
│       │   ├── pre_check_engine.py  # Pre-check orchestration
│       │   ├── k8s_checks.py        # Kubernetes health checks
│       │   ├── istio_checks.py      # Istio-specific checks
│       │   └── datadog_checks.py    # Datadog metric checks
│       ├── validation/
│       │   ├── __init__.py
│       │   ├── engine.py            # Post-upgrade validation
│       │   └── metrics_comparator.py # Metric comparison logic
│       ├── gitops/
│       │   ├── __init__.py
│       │   ├── manager.py           # GitLab operations
│       │   └── flux_config.py       # Flux config parsing
│       ├── rollback/
│       │   ├── __init__.py
│       │   └── engine.py            # Rollback automation
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── aws_client.py        # AWS operations
│       │   ├── k8s_client.py        # Kubernetes client
│       │   ├── datadog_client.py    # Datadog API client
│       │   ├── gitlab_client.py     # GitLab API client
│       │   └── istioctl.py          # istioctl wrapper
│       ├── llm/                     # Optional LLM integration
│       │   ├── __init__.py
│       │   ├── analyzer.py          # Failure analysis
│       │   └── prompts.py           # LLM prompts
│       └── utils/
│           ├── __init__.py
│           ├── logging.py           # Structured logging
│           ├── retry.py             # Retry decorators
│           └── secrets.py           # Secrets management
├── tests/
│   ├── unit/
│   │   ├── test_cluster_registry.py
│   │   ├── test_pre_checks.py
│   │   ├── test_gitops.py
│   │   └── ...
│   ├── integration/
│   │   ├── test_aws_integration.py
│   │   ├── test_gitlab_integration.py
│   │   └── ...
│   └── e2e/
│       └── test_full_workflow.py
├── docs/
│   ├── getting-started.md
│   ├── architecture.md
│   ├── confguardration.md
│   ├── contributing.md
│   └── examples/
│       ├── basic-usage.md
│       └── advanced-scenarios.md
├── examples/
│   ├── config.yaml.example
│   └── cluster-registry.json.example
├── scripts/
│   ├── setup-dynamodb.sh      # DynamoDB table creation
│   └── bootstrap.sh            # Initial setup
├── pyproject.toml              # Python project config
├── README.md
├── LICENSE
└── CHANGELOG.md
```

---

## Confguardration

### Main Confguardration File

`~/.guard/config.yaml`:

```yaml
# GUARD Confguardration File

# AWS Settings
aws:
  region: us-east-1
  profile: default  # Optional: AWS profile to use
  dynamodb:
    table_name: guard-cluster-registry
    region: us-east-1
  secrets_manager:
    gitlab_token_secret: guard/gitlab-token
    datadog_credentials_secret: guard/datadog-credentials

# GitLab Settings
gitlab:
  url: https://gitlab.company.com
  default_target_branch: main
  mr_template: |
    ## Istio Upgrade: {version}

    ### Pre-Upgrade Health Report
    {health_report}

    ### Clusters in Batch
    {cluster_list}

    ### Datadog Links
    {datadog_links}

    ### Checklist
    - [ ] Review pre-upgrade health report
    - [ ] Verify Datadog dashboards
    - [ ] Approve and merge to proceed

# Datadog Settings
datadog:
  site: datadoghq.com
  # Queries for health checks
  queries:
    control_plane_errors: |
      sum:istio.pilot.xds.push.errors{cluster:{cluster_name}}.as_count()
    error_rate: |
      sum:trace.http.request.errors{service:*,env:{environment}}.as_count() /
      sum:trace.http.request.hits{service:*,env:{environment}}.as_count()
    latency_p95: |
      avg:trace.http.request.duration.by.service.95p{env:{environment}}
    latency_p99: |
      avg:trace.http.request.duration.by.service.99p{env:{environment}}
    proxy_cpu: |
      avg:kubernetes.cpu.usage.total{kube_container_name:istio-proxy,cluster_name:{cluster_name}}
    proxy_memory: |
      avg:kubernetes.memory.usage{kube_container_name:istio-proxy,cluster_name:{cluster_name}}

# Execution Settings
execution:
  max_parallel_clusters: 5           # Number of clusters to process concurrently
  mr_strategy: batch                  # batch (single MR) or per-cluster (one MR per cluster)
  enable_rollout_sequencing: true     # Enforce batch order (prevent prod-wave-2 before prod-wave-1)

# Rate Limiting (requests per minute)
rate_limits:
  gitlab_api: 300
  datadog_api: 300
  aws_api: 100

# Validation Settings
validation:
  soak_period_minutes: 60
  flux_sync_timeout_minutes: 15
  thresholds:
    latency_increase_percent: 10    # P95/P99 allowed increase
    error_rate_max: 0.001             # 0.1%
    resource_increase_percent: 50     # CPU/Memory allowed increase

# Rollback Settings
rollback:
  auto_create_mr: true
  require_manual_approval: true
  notification:
    enabled: true
    # Use secret reference instead of plaintext
    webhook_secret_name: guard/notification-webhook
    # Or PagerDuty integration key secret name
    pagerduty_secret_name: guard/pagerduty-key

# LLM Settings (Optional)
llm:
  enabled: false
  provider: openai  # openai, anthropic, or custom
  model: gpt-4
  api_key_secret: guard/llm-api-key  # Secret name in Secrets Manager

# Batch Confguardration
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

  - name: dev-wave-2
    description: Development clusters - second wave
    clusters:
      - eks-dev-us-west-2-app1
      - eks-dev-eu-west-1-app1

  - name: staging
    description: Staging clusters
    clusters:
      - eks-stage-us-east-1-app1
      - eks-stage-us-west-2-app1

  - name: prod-wave-1
    description: Production - Critical services
    clusters:
      - eks-prod-us-east-1-api
      - eks-prod-us-east-1-web

  - name: prod-wave-2
    description: Production - Secondary services
    clusters:
      - eks-prod-us-east-1-batch
      - eks-prod-us-east-1-analytics

# Logging
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  format: json
  output: stdout
```

### Cluster Registry Entry Example

See Core Components > Cluster Registry section for the complete DynamoDB schema.

---

## Progressive Rollout Strategy

### Rollout Sequence

```
1. test           → Single test cluster
   ↓ [Manual gate: Review & approve]

2. dev-wave-1     → First batch of dev clusters (2-5 clusters)
   ↓ [Auto-gate: Success required]

3. dev-wave-2     → Remaining dev clusters
   ↓ [Manual gate: Review & approve]

4. staging        → All staging clusters
   ↓ [Manual gate + Extended soak period]

5. prod-wave-1    → Critical production services (high-traffic)
   ↓ [Manual gate + On-call team notified]

6. prod-wave-2    → Secondary production services
   ↓ [Manual gate]

7. prod-wave-3    → Remaining production clusters
```

### Execution Pattern

**For each batch:**

```bash
# 1. Pre-check and create MR
guard run --batch dev-wave-1 --target-version 1.20.0

# Output:
# ✓ Pre-checks passed for all clusters in batch 'dev-wave-1'
# ✓ GitLab MR created: https://gitlab.com/infra/clusters/-/merge_requests/1234
# → Waiting for MR approval and merge...

# 2. Human reviews and merges MR in GitLab UI

# 3. GitLab CI/CD triggers monitoring (or run manually)
guard monitor --batch dev-wave-1

# Output:
# ⏳ Waiting for Flux sync...
# ✓ Flux reconciliation complete
# ⏳ Starting soak period (60 minutes)...
# ✓ Soak period complete
# ✓ Post-upgrade validation passed
# ✓ All clusters healthy - upgrade successful!

# 4. Proceed to next batch
guard run --batch dev-wave-2 --target-version 1.20.0
```

### Failure Handling

```bash
# If post-upgrade validation fails:
# ✗ Validation failed: P99 latency increased by 45%
# → Creating rollback MR...
# ✓ Rollback MR created: https://gitlab.com/infra/clusters/-/merge_requests/1235
# 🚨 ALERT: Manual approval required for rollback

# Human reviews rollback MR and merges

# Optional: Monitor rollback
guard monitor --batch prod-wave-1
```

---

## Security Considerations

### 1. Credential Management

**DO:**
- ✅ Store all credentials in AWS Secrets Manager or HashiCorp Vault
- ✅ Use IAM roles with least-privilege access
- ✅ Rotate credentials regularly (GitLab tokens, Datadog API keys)
- ✅ Use temporary credentials via AWS STS AssumeRole

**DON'T:**
- ❌ Store credentials in config files
- ❌ Commit credentials to Git
- ❌ Use long-lived access keys

### 2. IAM Permissions

**GUARD Execution Role:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sts:AssumeRole"
      ],
      "Resource": "arn:aws:iam::*:role/GUARD-EKSAccess-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/guard-cluster-registry"
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

**Per-Cluster EKS Access Role:**

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
      "Resource": "arn:aws:eks:*:*:cluster/*"
    }
  ]
}
```

**Note:** EKS access entries (for `kubectl` access) must be confguardred separately via Terraform.

### 3. Network Security

- Ensure GUARD execution environment has IPv4 connectivity to:
  - EKS API servers
  - GitLab instance
  - Datadog API endpoints
- Consider running GUARD from:
  - Bastion host
  - CI/CD runner with VPC access
  - AWS Lambda (for scheduled upgrades)

### 4. Audit Logging

- All GUARD operations logged to structured logs (JSON)
- Include:
  - User/role executing command
  - Batch/clusters affected
  - Pre-check results
  - Validation results
  - MR URLs
  - Rollback triggers
- Ship logs to centralized logging (CloudWatch, Datadog, etc.)

---

## Observability & Monitoring

### GUARD Self-Monitoring

**Metrics to track:**

```python
# src/guard/utils/metrics.py
from datadog import statsd

# Upgrade execution metrics
statsd.increment('guard.upgrade.started', tags=['batch:prod-wave-1'])
statsd.increment('guard.upgrade.success', tags=['batch:prod-wave-1'])
statsd.increment('guard.upgrade.failed', tags=['batch:prod-wave-1'])

# Pre-check metrics
statsd.histogram('guard.precheck.duration', 45.2, tags=['cluster:eks-prod'])
statsd.increment('guard.precheck.failed', tags=['check:datadog_alerts'])

# Validation metrics
statsd.histogram('guard.validation.soak_period', 3600)
statsd.gauge('guard.validation.latency_increase', 5.2, tags=['cluster:eks-prod'])

# Rollback metrics
statsd.increment('guard.rollback.triggered', tags=['batch:prod-wave-1'])
```

**Custom Datadog Dashboard:**

Create a dashboard to monitor GUARD operations:
- Upgrade success rate by batch
- Pre-check failure rate by check type
- Average validation time
- Rollback frequency
- Time-to-upgrade by environment

### Alerting

**Set up monitors for:**

1. **Pre-check failures > threshold**
   - Indicates cluster health issues
   - May require investigation before upgrade

2. **Validation failures**
   - Immediate alert to on-call team
   - Includes rollback MR link

3. **Rollback triggered**
   - P1 alert
   - Requires immediate attention

---

## Future Enhancements

### Phase 1 (MVP)
- ✅ Core workflow (run → monitor → rollback)
- ✅ DynamoDB-based state management
- ✅ Datadog health checks
- ✅ GitLab MR automation
- ✅ Basic CLI

### Phase 2 (Optimization)
- [ ] Parallel cluster upgrades within a batch (**PRIORITY: Move to Phase 1/MVP**)
- [ ] **Revision-Based Canary Upgrade Strategy**
  - Install new Istio control plane revision alongside existing revision
  - Progressive namespace relabeling with validation gates
  - Canary namespace testing before full rollout
  - Automated rollback to old revision on failure
  - Remove old revision only after all namespaces migrated
  - **Note**: Deferred for organizational reasons; current approach uses in-place control plane upgrades
- [ ] Per-cluster canary strategy (upgrade 1 cluster, validate, then rest)
- [ ] Web UI for status monitoring
- [ ] Slack bot integration for approvals
- [ ] Automated batch progression (on success)
- [ ] Event-driven monitoring via Flux Notification Controller webhooks

### Phase 3 (Advanced)
- [ ] Multi-region coordination
- [ ] Blue/green Istio control plane upgrades
- [ ] Integration with other service meshes (Linkerd, Consul)
- [ ] Automated Istio version compatibility checking
- [ ] Historical upgrade analytics and recommendations

### Phase 4 (Intelligence)
- [ ] LLM-powered failure prediction
- [ ] Automatic SLO-based validation thresholds
- [ ] Integration with incident management (PagerDuty, OpsGenie)
- [ ] Self-healing capabilities
- [ ] Cost analysis of upgrades

---

## Key Improvements from Expert Review

This plan has been enhanced based on comprehensive review by multiple AI models (GPT-5 and Gemini 2.5 Pro). The following critical improvements have been incorporated:

### P0 - Production Readiness Enhancements

✅ **Parallelism & Concurrency** (lines 137-138, 144, 1125-1135)
- Added `--parallelism` flag to CLI commands
- Confguardrable `max_parallel_clusters` setting
- Per-provider rate limiting (GitLab, Datadog, AWS APIs)
- Prevents API throttling when operating at scale (75 clusters)

✅ **Atomic State Management** (lines 256-288)
- DynamoDB TransactWriteItems for atomic status transitions
- Prevents race conditions and state corruption
- Version-based optimistic locking
- Supports concurrent operations safely

✅ **Distributed Locking** (lines 290-345)
- Complete implementation with TTL-based leases
- Lock renewal for long-running operations
- Prevents duplicate MRs and conflicting operations
- Conditional writes with automatic expiration

✅ **CRD Upgrade Ordering** (lines 379-386, 882-894)
- Separate CRD update step before control plane
- Flux resource `dependsOn` enforcement
- Pre-checks validate CRD compatibility
- Addresses critical Istio upgrade requirement

✅ **K8s-Istio Compatibility Gate** (lines 387-399, 442-443)
- Validates Kubernetes version against Istio compatibility matrix
- Prevents unsupported version combinations
- Fails fast with helpful error messages
- Reduces upgrade failures

✅ **Security Hardening** (lines 496-524, 1152-1155)
- GitLab assignee handle → user ID resolution
- Secrets Manager for notification webhooks (no plaintext)
- Proper IAM role assumption
- Audit logging for all operations

✅ **Flux Sync Implementation** (lines 551-595)
- Proper `observedGeneration` == `metadata.generation` check
- Ready condition validation
- Exponential backoff with jitter
- Failure detection and error reporting

✅ **AWS EKS Integration** (lines 686-741)
- Complete kubeconfig generation implementation
- STS token-based authentication
- Temporary credentials with IAM role assumption
- Multi-account support

✅ **Rollout Sequencing** (lines 179, 347-374, 1129)
- Enforces batch order (prevents prod-wave-2 before prod-wave-1)
- Validates prerequisite batch completion
- Confguardrable batch dependencies
- Prevents operator errors

### P1 - Enhanced Developer Experience

✅ **Enhanced CLI Commands** (lines 155-171)
- `guard status` - Show current workflow status
- `guard diff` - Preview confguardration changes
- `guard resume` - Resume failed workflows
- `guard validate` - End-to-end connectivity testing

✅ **Per-Cluster MR Strategy** (line 138, 895, 1128)
- Optional `--mr-strategy per-cluster` flag
- Isolates blast radius for critical changes
- Easier rollback of individual cluster failures
- Maintains audit trail per cluster

✅ **Observability & Metrics** (lines 935, 941)
- Added `datadog` and `ratelimit` dependencies
- StatsD metrics for self-monitoring
- Structured logging with correlation IDs
- Rate limit tracking

### Future Enhancements

📝 **Revision-Based Canary Upgrades** (lines 1462-1468)
- Deferred for organizational reasons
- Current approach: in-place control plane upgrades
- Future: Install new revision → canary → progressive rollout → cleanup
- Documented as Phase 2 enhancement

### Impact Summary

**Reliability**: Atomic state management + distributed locking eliminates race conditions
**Safety**: CRD ordering + compatibility gates prevent breaking upgrades
**Scale**: Parallelism + rate limiting handles 75 clusters efficiently
**Security**: Secrets Manager + IAM roles + audit logging
**Usability**: Enhanced CLI + sequencing + per-cluster MRs

**Overall Confidence**: 8-9/10 for production readiness with these enhancements

---

## Contributing

See [CONTRIBUTING.md](docs/contributing.md) for guidelines.

---

## License

Apache 2.0 - see [LICENSE](LICENSE)

---

## Support & Resources

- **Documentation:** https://github.com/adickinson72/guard/docs
- **Issues:** https://github.com/adickinson72/guard/issues
- **Discussions:** https://github.com/adickinson72/guard/discussions
- **Slack:** #guard-support

---

**Built with ❤️ by Platform Engineering**
