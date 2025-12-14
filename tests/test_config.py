"""Tests for Redis Consumer and Trading Config.

These tests use the mocked Redis from conftest.py.
"""

import json
import pytest
from unittest.mock import MagicMock

# Import mock from conftest (already set up in sys.modules)
from conftest import mock_redis_client

from infrastructure.queue.redis_consumer import RedisConsumer


class TestRedisConsumer:
    """Test Redis queue consumer."""

    def setup_method(self):
        """Reset mocks before each test."""
        mock_redis_client.reset_mock()
        # Default mock returns
        mock_redis_client.sismember.return_value = False
        mock_redis_client.lrange.return_value = []

    def test_pop_task_success(self):
        """Test successful task pop from queue using brpoplpush."""
        raw_task = json.dumps({"thread_id": "t123", "thread_name": "SPY Signal"})
        mock_redis_client.brpoplpush.return_value = raw_task
        mock_redis_client.lrange.return_value = [raw_task]  # Only this task in processing

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=5)

        assert task is not None
        assert task["thread_id"] == "t123"
        assert "_raw_data" in task  # Should have raw data for later removal

    def test_pop_task_timeout(self):
        """Test task pop timeout (no tasks)."""
        mock_redis_client.brpoplpush.return_value = None

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        assert task is None

    def test_pop_task_invalid_json(self):
        """Test handling of invalid JSON in queue."""
        mock_redis_client.brpoplpush.return_value = "not valid json"

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        # Should return None and move to dead letter
        assert task is None
        mock_redis_client.lrem.assert_called()  # Remove from processing
        mock_redis_client.lpush.assert_called()  # Add to dead letter

    def test_pop_task_missing_thread_id(self):
        """Test handling of task without thread_id."""
        mock_redis_client.brpoplpush.return_value = json.dumps({"name": "no thread id"})

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        assert task is None
        mock_redis_client.lrem.assert_called()

    def test_pop_task_skips_completed(self):
        """Test that already completed tasks are skipped."""
        raw_task = json.dumps({"thread_id": "t123"})
        mock_redis_client.brpoplpush.return_value = raw_task
        mock_redis_client.sismember.return_value = True  # Already completed

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        assert task is None
        mock_redis_client.lrem.assert_called()  # Should be removed from processing

    def test_pop_task_skips_duplicate(self):
        """Test that duplicate tasks in processing are skipped."""
        raw_task = json.dumps({"thread_id": "t123"})
        mock_redis_client.brpoplpush.return_value = raw_task
        mock_redis_client.sismember.return_value = False
        # Same thread_id appears twice in processing (duplicate)
        mock_redis_client.lrange.return_value = [raw_task, raw_task]

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        assert task is None

    def test_complete_task(self):
        """Test marking task as complete."""
        raw_data = json.dumps({"thread_id": "t123"})

        consumer = RedisConsumer()
        consumer.complete_task("t123", raw_data)

        mock_redis_client.lrem.assert_called()  # Remove from processing list
        mock_redis_client.sadd.assert_called()  # Add to completed set

    def test_fail_task(self):
        """Test marking task as failed."""
        raw_data = json.dumps({"thread_id": "t123"})

        consumer = RedisConsumer()
        consumer.fail_task("t123", "Test error", raw_data)

        mock_redis_client.lrem.assert_called()
        mock_redis_client.hset.assert_called()

    def test_get_stats(self):
        """Test getting queue statistics."""
        mock_redis_client.llen.side_effect = [5, 2, 0]  # pending, processing, dead_letter
        mock_redis_client.zcard.return_value = 1  # scheduled
        mock_redis_client.scard.return_value = 10  # completed
        mock_redis_client.hlen.return_value = 1  # failed

        consumer = RedisConsumer()
        stats = consumer.get_stats()

        assert stats["pending"] == 5
        assert stats["processing"] == 2
        assert stats["scheduled"] == 1
        assert stats["completed"] == 10
        assert stats["failed"] == 1
        assert stats["dead_letter"] == 0


class TestTradingConfig:
    """Test trading configuration from Redis.

    Note: Since we mock Redis at module level, we just verify the class
    has the expected property definitions.
    """

    def test_config_class_has_expected_properties(self):
        """Test that TradingConfig class has expected properties defined."""
        from config.redis_config import TradingConfig

        # Verify the class has these as properties (not instance values)
        assert hasattr(TradingConfig, "emergency_stop")
        assert hasattr(TradingConfig, "whitelist_tickers")
        assert hasattr(TradingConfig, "blacklist_tickers")
        assert hasattr(TradingConfig, "execute_orders")
        assert hasattr(TradingConfig, "max_concurrent_positions")

    def test_defaults_dict_exists(self):
        """Test that DEFAULTS dict exists on TradingConfig."""
        from config.redis_config import TradingConfig

        # Just verify DEFAULTS exists as a class attribute
        # Actual values tested in integration tests
        assert hasattr(TradingConfig, "DEFAULTS")
