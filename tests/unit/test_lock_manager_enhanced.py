"""Unit tests for enhanced lock manager with fencing tokens."""

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from guard.core.exceptions import LockAcquisitionError
from guard.registry.lock_manager import LockManager


class TestLockManagerFencingTokens:
    """Test lock manager fencing token functionality."""

    @patch("guard.registry.lock_manager.boto3")
    def test_acquire_lock_with_fencing_token(self, mock_boto3):
        """Test lock acquisition returns fencing token."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock successful lock acquisition
        mock_table.put_item.return_value = {}
        lock_manager.check_lock = MagicMock(return_value=None)

        owner, fencing_token = lock_manager.acquire_lock("resource-1")

        assert owner is not None
        assert fencing_token == 1  # First lock gets token 1

        # Verify fencing token was stored
        call_args = mock_table.put_item.call_args
        assert call_args[1]["Item"]["fencing_token"] == 1

    @patch("guard.registry.lock_manager.boto3")
    def test_fencing_token_increments(self, mock_boto3):
        """Test fencing token increments on subsequent locks."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock existing lock with token 5
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": "old-owner",
                "fencing_token": 5,
                "expiry_time": (datetime.utcnow() - timedelta(seconds=10)).isoformat(),
            }
        )

        owner, fencing_token = lock_manager.acquire_lock("resource-1")

        assert fencing_token == 6  # Should increment from 5 to 6

    @patch("guard.registry.lock_manager.boto3")
    def test_extend_lock_requires_fencing_token(self, mock_boto3):
        """Test lock extension requires matching fencing token."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock existing lock
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": "test-owner",
                "fencing_token": 10,
                "expiry_time": datetime.utcnow().isoformat(),
            }
        )

        # Should succeed with correct token
        lock_manager.extend_lock("resource-1", "test-owner", fencing_token=10)

        # Verify condition included fencing token
        call_args = mock_table.update_item.call_args
        assert ":token" in call_args[1]["ExpressionAttributeValues"]
        assert call_args[1]["ExpressionAttributeValues"][":token"] == 10

    @patch("guard.registry.lock_manager.boto3")
    def test_extend_lock_fails_with_wrong_token(self, mock_boto3):
        """Test lock extension fails with wrong fencing token."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock existing lock
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": "test-owner",
                "fencing_token": 10,
                "expiry_time": datetime.utcnow().isoformat(),
            }
        )

        # Should fail with wrong token
        with pytest.raises(LockAcquisitionError, match="token mismatch"):
            lock_manager.extend_lock("resource-1", "test-owner", fencing_token=9)


class TestLockManagerAutoRenewal:
    """Test automatic lock renewal functionality."""

    @patch("guard.registry.lock_manager.boto3")
    def test_auto_renew_lock_basic(self, mock_boto3):
        """Test basic auto-renewal functionality."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock successful renewal
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": "test-owner",
                "fencing_token": 5,
                "expiry_time": datetime.utcnow().isoformat(),
            }
        )
        lock_manager.extend_lock = MagicMock()

        # Create stop event
        stop_event = threading.Event()

        # Start auto-renewal in background
        renewal_thread = threading.Thread(
            target=lock_manager.auto_renew_lock,
            args=("resource-1", "test-owner", 5),
            kwargs={"renewal_interval": 0.5, "stop_event": stop_event},
        )
        renewal_thread.start()

        # Let it run for a bit
        time.sleep(1.2)

        # Stop renewal
        stop_event.set()
        renewal_thread.join(timeout=2.0)

        # Should have called extend_lock at least once
        assert lock_manager.extend_lock.call_count >= 1

    @patch("guard.registry.lock_manager.boto3")
    def test_auto_renew_stops_on_failure(self, mock_boto3):
        """Test auto-renewal stops when extension fails."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Mock renewal failure
        lock_manager.extend_lock = MagicMock(side_effect=LockAcquisitionError("Lock lost"))

        stop_event = threading.Event()

        # Start auto-renewal
        renewal_thread = threading.Thread(
            target=lock_manager.auto_renew_lock,
            args=("resource-1", "test-owner", 5),
            kwargs={"renewal_interval": 0.2, "stop_event": stop_event},
        )
        renewal_thread.start()

        # Wait for thread to finish (should stop on error)
        renewal_thread.join(timeout=2.0)

        # Thread should have stopped
        assert not renewal_thread.is_alive()


class TestLockManagerAtomicity:
    """Test atomic lock operations."""

    @patch("guard.registry.lock_manager.boto3")
    def test_acquire_lock_prevents_double_acquisition(self, mock_boto3):
        """Test lock cannot be acquired twice simultaneously."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # First acquisition succeeds
        lock_manager.check_lock = MagicMock(return_value=None)
        owner1, token1 = lock_manager.acquire_lock("resource-1")

        # Second acquisition should fail (condition check fails)
        error_response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        mock_table.put_item.side_effect = ClientError(error_response, "PutItem")

        with pytest.raises(LockAcquisitionError, match="already held"):
            lock_manager.acquire_lock("resource-1", wait=False)

    @patch("guard.registry.lock_manager.boto3")
    def test_lock_prevents_aba_problem(self, mock_boto3):
        """Test fencing token prevents ABA problem."""
        mock_table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = mock_table

        lock_manager = LockManager("test-locks", region="us-east-1")

        # Scenario: Process A acquires lock (token 1)
        lock_manager.check_lock = MagicMock(return_value=None)
        owner_a, token_a = lock_manager.acquire_lock("resource-1")
        assert token_a == 1

        # Process A pauses, lock expires and Process B acquires (token 2)
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": "old-owner",
                "fencing_token": 1,
                "expiry_time": (datetime.utcnow() - timedelta(seconds=10)).isoformat(),
            }
        )
        owner_b, token_b = lock_manager.acquire_lock("resource-1")
        assert token_b == 2

        # Process A wakes up and tries to extend with old token (should fail)
        lock_manager.check_lock = MagicMock(
            return_value={
                "resource_id": "resource-1",
                "owner": owner_b,
                "fencing_token": 2,
                "expiry_time": datetime.utcnow().isoformat(),
            }
        )

        # Should fail because owner doesn't match (Process B owns it now)
        with pytest.raises(LockAcquisitionError):
            lock_manager.extend_lock("resource-1", owner_a, fencing_token=1)
