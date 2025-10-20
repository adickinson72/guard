"""Secrets management utilities for GUARD."""

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class SecretsManager:
    """AWS Secrets Manager client."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize Secrets Manager client.

        Args:
            region: AWS region
        """
        self.client = boto3.client("secretsmanager", region_name=region)
        self.region = region
        logger.debug("secrets_manager_initialized", region=region)

    def get_secret(self, secret_name: str) -> str:
        """Get secret value from Secrets Manager.

        Args:
            secret_name: Name of the secret

        Returns:
            Secret value as string

        Raises:
            AWSError: If secret cannot be retrieved
        """
        try:
            logger.debug("getting_secret", secret_name=secret_name)
            response = self.client.get_secret_value(SecretId=secret_name)

            # Secrets can be stored as either SecretString or SecretBinary
            if "SecretString" in response:
                secret = response["SecretString"]
            else:
                secret = response["SecretBinary"].decode("utf-8")

            logger.info("secret_retrieved", secret_name=secret_name)
            return secret

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(
                "secret_retrieval_failed",
                secret_name=secret_name,
                error_code=error_code,
            )

            if error_code == "ResourceNotFoundException":
                raise AWSError(f"Secret not found: {secret_name}") from e
            elif error_code == "InvalidRequestException":
                raise AWSError(f"Invalid secret request: {secret_name}") from e
            elif error_code == "InvalidParameterException":
                raise AWSError(f"Invalid secret parameter: {secret_name}") from e
            else:
                raise AWSError(f"Failed to retrieve secret {secret_name}: {error_code}") from e

    def get_secret_json(self, secret_name: str) -> dict[str, Any]:
        """Get secret value as JSON object.

        Args:
            secret_name: Name of the secret

        Returns:
            Secret value as dictionary

        Raises:
            AWSError: If secret cannot be retrieved or parsed
        """
        try:
            secret_string = self.get_secret(secret_name)
            return json.loads(secret_string)
        except json.JSONDecodeError as e:
            logger.error(
                "secret_json_parse_failed",
                secret_name=secret_name,
                error=str(e),
            )
            raise AWSError(f"Failed to parse secret as JSON: {secret_name}") from e

    def put_secret(self, secret_name: str, secret_value: str) -> None:
        """Store or update a secret in Secrets Manager.

        Args:
            secret_name: Name of the secret
            secret_value: Secret value to store

        Raises:
            AWSError: If secret cannot be stored
        """
        try:
            logger.debug("putting_secret", secret_name=secret_name)

            # Try to update existing secret first
            try:
                self.client.put_secret_value(SecretId=secret_name, SecretString=secret_value)
                logger.info("secret_updated", secret_name=secret_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    # Secret doesn't exist, create it
                    self.client.create_secret(Name=secret_name, SecretString=secret_value)
                    logger.info("secret_created", secret_name=secret_name)
                else:
                    raise

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(
                "secret_put_failed",
                secret_name=secret_name,
                error_code=error_code,
            )
            raise AWSError(f"Failed to store secret {secret_name}: {error_code}") from e

    def delete_secret(self, secret_name: str, force_delete: bool = False) -> None:
        """Delete a secret from Secrets Manager.

        Args:
            secret_name: Name of the secret
            force_delete: If True, delete immediately without recovery window

        Raises:
            AWSError: If secret cannot be deleted
        """
        try:
            logger.debug(
                "deleting_secret",
                secret_name=secret_name,
                force_delete=force_delete,
            )

            kwargs: dict[str, Any] = {"SecretId": secret_name}
            if force_delete:
                kwargs["ForceDeleteWithoutRecovery"] = True
            else:
                kwargs["RecoveryWindowInDays"] = 7

            self.client.delete_secret(**kwargs)
            logger.info("secret_deleted", secret_name=secret_name)

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(
                "secret_deletion_failed",
                secret_name=secret_name,
                error_code=error_code,
            )

            if error_code == "ResourceNotFoundException":
                # Secret doesn't exist, which is fine
                logger.warning("secret_not_found", secret_name=secret_name)
                return

            raise AWSError(f"Failed to delete secret {secret_name}: {error_code}") from e
