"""Configuration management for GUARD."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from guard.core.exceptions import ConfigurationError


class AWSConfig(BaseModel):
    """AWS configuration."""

    region: str = "us-east-1"
    profile: str | None = None

    class DynamoDBConfig(BaseModel):
        """DynamoDB configuration."""

        table_name: str = "guard-cluster-registry"
        region: str = "us-east-1"

    class SecretsManagerConfig(BaseModel):
        """Secrets Manager configuration."""

        gitlab_token_secret: str = "guard/gitlab-token"
        datadog_credentials_secret: str = "guard/datadog-credentials"

    dynamodb: DynamoDBConfig = Field(default_factory=DynamoDBConfig)
    secrets_manager: SecretsManagerConfig = Field(default_factory=SecretsManagerConfig)


class GitLabConfig(BaseModel):
    """GitLab configuration."""

    url: str
    default_target_branch: str = "main"
    mr_template: str = """## Istio Upgrade: {version}

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
"""


class DatadogQueryConfig(BaseModel):
    """Datadog query configuration."""

    control_plane_errors: str = (
        "sum:istio.pilot.xds.push.errors{{cluster:{cluster_name}}}.as_count()"
    )
    error_rate: str = """sum:trace.http.request.errors{{service:*,env:{environment}}}.as_count() /
sum:trace.http.request.hits{{service:*,env:{environment}}}.as_count()"""
    latency_p95: str = "avg:trace.http.request.duration.by.service.95p{{env:{environment}}}"
    latency_p99: str = "avg:trace.http.request.duration.by.service.99p{{env:{environment}}}"
    proxy_cpu: str = "avg:kubernetes.cpu.usage.total{{kube_container_name:istio-proxy,cluster_name:{cluster_name}}}"
    proxy_memory: str = (
        "avg:kubernetes.memory.usage{{kube_container_name:istio-proxy,cluster_name:{cluster_name}}}"
    )


class DatadogConfig(BaseModel):
    """Datadog configuration."""

    site: str = "datadoghq.com"
    queries: DatadogQueryConfig = Field(default_factory=DatadogQueryConfig)


class ValidationThresholdsConfig(BaseModel):
    """Validation thresholds configuration."""

    latency_increase_percent: float = 10.0
    error_rate_max: float = 0.001
    resource_increase_percent: float = 50.0


class ExecutionConfig(BaseModel):
    """Execution configuration."""

    max_parallel_clusters: int = 5
    mr_strategy: str = "batch"  # batch or per-cluster
    enable_rollout_sequencing: bool = True


class RateLimitsConfig(BaseModel):
    """Rate limiting configuration."""

    gitlab_api: int = 300  # requests per minute
    datadog_api: int = 300
    aws_api: int = 100


class ValidationConfig(BaseModel):
    """Validation configuration."""

    soak_period_minutes: int = 60
    flux_sync_timeout_minutes: int = 15
    thresholds: ValidationThresholdsConfig = Field(default_factory=ValidationThresholdsConfig)


class NotificationConfig(BaseModel):
    """Notification configuration."""

    enabled: bool = True
    webhook_secret_name: str | None = None  # AWS Secrets Manager secret name
    pagerduty_secret_name: str | None = None


class RollbackConfig(BaseModel):
    """Rollback configuration."""

    auto_create_mr: bool = True
    require_manual_approval: bool = True
    notification: NotificationConfig = Field(default_factory=NotificationConfig)


class LLMConfig(BaseModel):
    """LLM configuration."""

    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4"
    api_key_secret: str = "guard/llm-api-key"


class BatchConfig(BaseModel):
    """Batch configuration."""

    name: str
    description: str
    clusters: list[str]


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"


class GuardConfig(BaseModel):
    """Main GUARD configuration."""

    aws: AWSConfig
    gitlab: GitLabConfig
    datadog: DatadogConfig = Field(default_factory=DatadogConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    rate_limits: RateLimitsConfig = Field(default_factory=RateLimitsConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    batches: list[BatchConfig] = Field(default_factory=list)
    batch_order: dict[str, list[str]] = Field(default_factory=dict)  # Batch prerequisites
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_file(cls, path: str | Path) -> "GuardConfig":
        """Load configuration from YAML file.

        Args:
            path: Path to configuration file

        Returns:
            GuardConfig instance

        Raises:
            ConfigurationError: If file cannot be loaded or parsed
        """
        config_path = Path(path).expanduser()

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with config_path.open() as f:
                data = yaml.safe_load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}") from e

        try:
            return cls(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid configuration: {e}") from e

    def get_batch(self, batch_name: str) -> BatchConfig | None:
        """Get batch configuration by name.

        Args:
            batch_name: Name of the batch

        Returns:
            BatchConfig if found, None otherwise
        """
        return next((b for b in self.batches if b.name == batch_name), None)

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation
        """
        return self.model_dump()
