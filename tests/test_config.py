"""Tests for Redis Consumer and Trading Config."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestRedisConsumer:
    """Test Redis queue consumer."""

    def test_pop_task_success(self):
        """Test successful task pop from queue."""
        mock_redis = MagicMock()
        mock_redis.brpop.return_value = (
            "queue:threads:pending",
            json.dumps({"thread_id": "t123", "thread_name": "SPY Signal"}),
        )

        with patch("redis.from_url", return_value=mock_redis):
            from infrastructure.queue.redis_consumer import RedisConsumer

            consumer = RedisConsumer()
            task = consumer.pop_task(timeout=5)

            assert task is not None
            assert task["thread_id"] == "t123"

    def test_pop_task_timeout(self):
        """Test task pop timeout (no tasks)."""
        mock_redis = MagicMock()
        mock_redis.brpop.return_value = None

        with patch("redis.from_url", return_value=mock_redis):
            from infrastructure.queue.redis_consumer import RedisConsumer

            consumer = RedisConsumer()
            task = consumer.pop_task(timeout=1)

            assert task is None

    def test_complete_task(self):
        """Test marking task as complete."""
        mock_redis = MagicMock()

        with patch("redis.from_url", return_value=mock_redis):
            from infrastructure.queue.redis_consumer import RedisConsumer

            consumer = RedisConsumer()
            consumer.complete_task("t123")

            mock_redis.srem.assert_called()
            mock_redis.sadd.assert_called()

    def test_get_stats(self):
        """Test getting queue statistics."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 5
        mock_redis.scard.side_effect = [2, 10]
        mock_redis.hlen.return_value = 1

        with patch("redis.from_url", return_value=mock_redis):
            from infrastructure.queue.redis_consumer import RedisConsumer

            consumer = RedisConsumer()
            stats = consumer.get_stats()

            assert stats["pending"] == 5


class TestTradingConfig:
    """Test trading configuration from Redis."""

    def test_default_values(self):
        """Test that default values are set."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = False
        mock_redis.get.return_value = None

        with patch("redis.from_url", return_value=mock_redis):
            from config.redis_config import TradingConfig

            config = TradingConfig()

            assert config.max_daily_trades == 10
            assert config.emergency_stop is False

    def test_set_unknown_key_rejected(self):
        """Test that unknown keys are rejected."""
        mock_redis = MagicMock()
        mock_redis.exists.return_value = True

        with patch("redis.from_url", return_value=mock_redis):
            from config.redis_config import TradingConfig

            config = TradingConfig()
            result = config.set("unknown_key", "value")

            assert result is False
