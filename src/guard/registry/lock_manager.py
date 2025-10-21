"""Distributed lock manager using DynamoDB."""

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from guard.core.exceptions import AWSError, LockAcquisitionError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class LockManager:
    """DynamoDB-based distributed lock manager."""

    def __init__(self, table_name: str, region: str = "us-east-1"):
        """Initialize lock manager.

        Args:
            table_name: DynamoDB table name for locks
            region: AWS region
        """
        self.table_name = table_name
        self.region = region

        try:
            dynamodb = boto3.resource("dynamodb", region_name=region)
            self.table = dynamodb.Table(table_name)

            logger.debug(
                "lock_manager_initialized",
                table_name=table_name,
                region=region,
            )

        except ClientError as e:
            logger.error(
                "lock_manager_init_failed",
                table_name=table_name,
                error=str(e),
            )
            raise AWSError(f"Failed to initialize lock manager: {e}") from e

    def acquire_lock(
        self,
        resource_id: str,
        owner: str | None = None,
        timeout: int = 300,
        wait: bool = False,
        wait_timeout: int = 60,
    ) -> tuple[str, int]:
        """Acquire a distributed lock with fencing token.

        Args:
            resource_id: Identifier for the resource to lock
            owner: Lock owner identifier (generated if not provided)
            timeout: Lock timeout in seconds (default: 5 minutes)
            wait: Wait for lock if unavailable (default: False)
            wait_timeout: Maximum time to wait for lock in seconds

        Returns:
            Tuple of (lock_token, fencing_token) - fencing token prevents ABA

        Raises:
            LockAcquisitionError: If lock cannot be acquired
            AWSError: If DynamoDB operation fails
        """
        if not owner:
            owner = str(uuid.uuid4())

        expiry_time = datetime.utcnow() + timedelta(seconds=timeout)

        logger.debug(
            "acquiring_lock",
            resource_id=resource_id,
            owner=owner,
            timeout=timeout,
        )

        start_time = time.time()

        while True:
            try:
                # Get current fencing token (if lock exists)
                current_lock = self.check_lock(resource_id)
                next_fencing_token = current_lock.get("fencing_token", 0) + 1 if current_lock else 1

                # Try to acquire lock with fencing token
                self.table.put_item(
                    Item={
                        "resource_id": resource_id,
                        "owner": owner,
                        "expiry_time": expiry_time.isoformat(),
                        "acquired_at": datetime.utcnow().isoformat(),
                        "fencing_token": next_fencing_token,
                    },
                    ConditionExpression="attribute_not_exists(resource_id) OR expiry_time < :now",
                    ExpressionAttributeValues={":now": datetime.utcnow().isoformat()},
                )

                logger.info(
                    "lock_acquired",
                    resource_id=resource_id,
                    owner=owner,
                    fencing_token=next_fencing_token,
                )
                return owner, next_fencing_token

            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    # Lock is held by someone else
                    if not wait:
                        logger.warning(
                            "lock_acquisition_failed",
                            resource_id=resource_id,
                            reason="lock_held",
                        )
                        raise LockAcquisitionError(
                            f"Lock for {resource_id} is already held"
                        ) from None

                    # Check if we've exceeded wait timeout
                    elapsed = time.time() - start_time
                    if elapsed > wait_timeout:
                        logger.error(
                            "lock_acquisition_timeout",
                            resource_id=resource_id,
                            elapsed=elapsed,
                        )
                        raise LockAcquisitionError(
                            f"Timeout waiting for lock on {resource_id}"
                        ) from None

                    # Wait and retry
                    logger.debug("waiting_for_lock", resource_id=resource_id)
                    time.sleep(1)
                else:
                    logger.error(
                        "lock_acquisition_error",
                        resource_id=resource_id,
                        error=str(e),
                    )
                    raise AWSError(f"Failed to acquire lock: {e}") from e

    def release_lock(self, resource_id: str, owner: str) -> None:
        """Release a distributed lock.

        Args:
            resource_id: Resource identifier
            owner: Lock owner (must match the lock holder)

        Raises:
            LockAcquisitionError: If lock is not held by owner
            AWSError: If DynamoDB operation fails
        """
        try:
            logger.debug(
                "releasing_lock",
                resource_id=resource_id,
                owner=owner,
            )

            # Only delete if owner matches
            self.table.delete_item(
                Key={"resource_id": resource_id},
                ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={":owner": owner},
            )

            logger.info("lock_released", resource_id=resource_id, owner=owner)

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(
                    "lock_release_failed",
                    resource_id=resource_id,
                    reason="owner_mismatch",
                )
                raise LockAcquisitionError(
                    f"Lock for {resource_id} is not held by {owner}"
                ) from None
            else:
                logger.error(
                    "lock_release_error",
                    resource_id=resource_id,
                    error=str(e),
                )
                raise AWSError(f"Failed to release lock: {e}") from e

    def check_lock(self, resource_id: str) -> dict[str, Any] | None:
        """Check if a lock exists and get its details.

        Args:
            resource_id: Resource identifier

        Returns:
            Lock details dict or None if no lock exists

        Raises:
            AWSError: If DynamoDB operation fails
        """
        try:
            logger.debug("checking_lock", resource_id=resource_id)

            response = self.table.get_item(Key={"resource_id": resource_id})

            if "Item" not in response:
                logger.debug("lock_not_found", resource_id=resource_id)
                return None

            lock_info = response["Item"]

            # Check if lock is expired
            expiry_time_str = lock_info["expiry_time"]
            if not isinstance(expiry_time_str, str):
                logger.error("invalid_expiry_time_type", resource_id=resource_id)
                raise AWSError("Invalid expiry_time type in lock record")
            expiry_time = datetime.fromisoformat(expiry_time_str)
            if expiry_time < datetime.utcnow():
                logger.debug("lock_expired", resource_id=resource_id)
                # Clean up expired lock
                self.table.delete_item(Key={"resource_id": resource_id})
                return None

            logger.debug("lock_exists", resource_id=resource_id, lock_info=lock_info)
            return lock_info

        except Exception as e:
            logger.error("check_lock_failed", resource_id=resource_id, error=str(e))
            raise AWSError(f"Failed to check lock: {e}") from e

    def extend_lock(
        self, resource_id: str, owner: str, fencing_token: int, additional_seconds: int = 300
    ) -> None:
        """Extend the expiry time of an existing lock.

        Args:
            resource_id: Resource identifier
            owner: Lock owner (must match)
            fencing_token: Fencing token (must match)
            additional_seconds: Additional seconds to extend lock

        Raises:
            LockAcquisitionError: If lock doesn't exist or owner doesn't match
            AWSError: If DynamoDB operation fails
        """
        try:
            logger.debug(
                "extending_lock",
                resource_id=resource_id,
                owner=owner,
                fencing_token=fencing_token,
                additional_seconds=additional_seconds,
            )

            # Get current lock
            lock_info = self.check_lock(resource_id)
            if not lock_info:
                raise LockAcquisitionError(f"Lock for {resource_id} does not exist")

            if lock_info["owner"] != owner:
                raise LockAcquisitionError(f"Lock for {resource_id} is not held by {owner}")

            if lock_info.get("fencing_token") != fencing_token:
                raise LockAcquisitionError(f"Lock fencing token mismatch for {resource_id}")

            # Calculate new expiry
            current_expiry = datetime.fromisoformat(lock_info["expiry_time"])
            new_expiry = current_expiry + timedelta(seconds=additional_seconds)

            # Update expiry time
            self.table.update_item(
                Key={"resource_id": resource_id},
                UpdateExpression="SET expiry_time = :new_expiry",
                ConditionExpression="#owner = :owner AND fencing_token = :token",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":token": fencing_token,
                    ":new_expiry": new_expiry.isoformat(),
                },
            )

            logger.info("lock_extended", resource_id=resource_id, new_expiry=new_expiry)

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise LockAcquisitionError(
                    f"Lock for {resource_id} is not held by {owner} or token mismatch"
                ) from None
            else:
                logger.error(
                    "lock_extension_error",
                    resource_id=resource_id,
                    error=str(e),
                )
                raise AWSError(f"Failed to extend lock: {e}") from e

    def auto_renew_lock(
        self,
        resource_id: str,
        owner: str,
        fencing_token: int,
        renewal_interval: int = 60,
        stop_event: Any | None = None,
    ) -> None:
        """Automatically renew a lock in the background.

        This method runs in a loop, renewing the lock at the specified interval
        until the stop_event is set or an error occurs.

        Args:
            resource_id: Resource identifier
            owner: Lock owner
            fencing_token: Fencing token
            renewal_interval: Seconds between renewals (default: 60)
            stop_event: Threading event to signal stop (optional)

        Raises:
            LockAcquisitionError: If renewal fails
            AWSError: If DynamoDB operation fails
        """
        import threading

        if stop_event is None:
            stop_event = threading.Event()

        logger.info(
            "starting_auto_renew",
            resource_id=resource_id,
            renewal_interval=renewal_interval,
        )

        try:
            while not stop_event.is_set():
                # Wait for renewal interval or stop signal
                if stop_event.wait(timeout=renewal_interval):
                    break

                # Renew the lock
                try:
                    self.extend_lock(
                        resource_id=resource_id,
                        owner=owner,
                        fencing_token=fencing_token,
                        additional_seconds=renewal_interval * 2,  # 2x buffer
                    )
                    logger.debug(
                        "lock_renewed",
                        resource_id=resource_id,
                        interval=renewal_interval,
                    )
                except LockAcquisitionError as e:
                    logger.error(
                        "lock_renewal_failed",
                        resource_id=resource_id,
                        error=str(e),
                    )
                    # Stop renewal on failure
                    break

        finally:
            logger.info("stopping_auto_renew", resource_id=resource_id)
