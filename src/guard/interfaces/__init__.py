"""Interface definitions for GUARD black box design."""

from guard.interfaces.check import Check, CheckContext
from guard.interfaces.cloud_provider import CloudProvider
from guard.interfaces.config_updater import ConfigUpdater
from guard.interfaces.gitops_provider import GitOpsProvider, MergeRequestInfo
from guard.interfaces.kubernetes_provider import (
    DeploymentInfo,
    KubernetesProvider,
    NodeInfo,
    PodInfo,
)
from guard.interfaces.metrics_provider import MetricPoint, MetricsProvider
from guard.interfaces.state_store import StateStore
from guard.interfaces.validator import MetricsSnapshot, Validator

__all__ = [
    "Check",
    "CheckContext",
    "CloudProvider",
    "ConfigUpdater",
    "DeploymentInfo",
    "GitOpsProvider",
    "KubernetesProvider",
    "MergeRequestInfo",
    "MetricPoint",
    "MetricsProvider",
    "MetricsSnapshot",
    "NodeInfo",
    "PodInfo",
    "StateStore",
    "Validator",
]
