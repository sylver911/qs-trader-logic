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

    def test_pop_task_success(self):
        """Test successful task pop from queue."""
        mock_redis_client.brpop.return_value = (
            "queue:threads:pending",
            json.dumps({"thread_id": "t123", "thread_name": "SPY Signal"}),
        )

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=5)

        assert task is not None
        assert task["thread_id"] == "t123"

    def test_pop_task_timeout(self):
        """Test task pop timeout (no tasks)."""
        mock_redis_client.brpop.return_value = None

        consumer = RedisConsumer()
        task = consumer.pop_task(timeout=1)

        assert task is None

    def test_complete_task(self):
        """Test marking task as complete."""
        consumer = RedisConsumer()
        consumer.complete_task("t123")

        mock_redis_client.srem.assert_called()
        mock_redis_client.sadd.assert_called()

    def test_get_stats(self):
        """Test getting queue statistics."""
        mock_redis_client.llen.return_value = 5
        mock_redis_client.scard.side_effect = [2, 10]
        mock_redis_client.hlen.return_value = 1

        consumer = RedisConsumer()
        stats = consumer.get_stats()

        assert stats["pending"] == 5


class TestTradingConfig:
    """Test trading configuration from Redis.

    Note: Since we mock Redis at module level, the trading_config singleton
    will have MagicMock attributes. We just verify the attributes exist.
    """

    def test_config_has_expected_attributes(self):
        """Test that trading config has expected attributes."""
        # Import the trading_config singleton which uses our mocked Redis
        from config.redis_config import trading_config

        # Verify it has the expected attributes (regardless of values)
        # With our mocking, these will be MagicMock objects
        assert hasattr(trading_config, "max_daily_trades")
        assert hasattr(trading_config, "emergency_stop")
        assert hasattr(trading_config, "whitelist_tickers")
        assert hasattr(trading_config, "blacklist_tickers")
        assert hasattr(trading_config, "execute_orders")
