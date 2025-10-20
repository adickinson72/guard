"""Adapter implementations for external services."""

from guard.adapters.aws_adapter import AWSAdapter
from guard.adapters.datadog_adapter import DatadogAdapter
from guard.adapters.dynamodb_adapter import DynamoDBAdapter
from guard.adapters.gitlab_adapter import GitLabAdapter
from guard.adapters.k8s_adapter import KubernetesAdapter

__all__ = [
    "AWSAdapter",
    "DatadogAdapter",
    "DynamoDBAdapter",
    "GitLabAdapter",
    "KubernetesAdapter",
]
