"""Data types for CloudProvider interface."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class CloudCredentials:
    """Cloud provider credentials."""

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime | None = None


@dataclass
class ClusterInfo:
    """Cloud cluster information."""

    endpoint: str
    ca_certificate: str
    version: str | None = None
    status: str | None = None
    arn: str | None = None
    name: str | None = None


@dataclass
class ClusterToken:
    """Cluster authentication token."""

    token: str
    expiration: datetime | None = None
    endpoint: str | None = None
    ca_data: str | None = None
