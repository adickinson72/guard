"""Interface definitions for IGU black box design."""

from guard.interfaces.check import Check, CheckContext
from guard.interfaces.cloud_provider import CloudProvider
from guard.interfaces.config_updater import ConfigUpdater
from guard.interfaces.gitops_provider import GitOpsProvider, MergeRequestInfo
from guard.interfaces.kubernetes_provider import (
    KubernetesProvider,
    PodInfo,
    DeploymentInfo,
    NodeInfo,
)
from guard.interfaces.metrics_provider import MetricsProvider, MetricPoint
from guard.interfaces.state_store import StateStore
from guard.interfaces.validator import Validator, MetricsSnapshot

__all__ = [
    "Check",
    "CheckContext",
    "CloudProvider",
    "ConfigUpdater",
    "GitOpsProvider",
    "MergeRequestInfo",
    "KubernetesProvider",
    "PodInfo",
    "DeploymentInfo",
    "NodeInfo",
    "MetricsProvider",
    "MetricPoint",
    "StateStore",
    "Validator",
    "MetricsSnapshot",
]
