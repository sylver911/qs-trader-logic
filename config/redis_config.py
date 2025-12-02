"""Trading configuration from Redis with defaults."""

import json
import logging
from typing import Any, Dict, List, Optional

import redis

from config.settings import config

logger = logging.getLogger(__name__)


class TradingConfig:
    """Trading parameters stored in Redis with defaults."""

    # Default values
    DEFAULTS = {
        "max_loss_per_trade_percent": 0.1,
        "max_daily_trades": 10,
        "max_concurrent_positions": 5,
        "max_loss_per_day_percent": 0.1,
        "default_stop_loss_percent": 0.3,
        "default_take_profit_percent": 0.5,
        "trailing_stop_enabled": False,
        "trailing_stop_activation_percent": 0.2,
        "trailing_stop_distance_percent": 0.1,
        "min_ai_confidence_score": 0.5,
        "blacklist_tickers": ["GME", "BYND"],
        "whitelist_tickers": ["SPY", "QQQ"],
        "max_position_size_percent": 0.2,
        "emergency_stop": False,
        "max_vix_level": 25,
        "current_llm_model": "deepseek/deepseek-reasoner",
        "execute_orders": False,  # If False, simulates orders without sending to IBeam
    }

    def __init__(self, redis_url: str = None):
        """Initialize trading config.

        Args:
            redis_url: Redis connection URL
        """
        self._redis_url = redis_url or config.REDIS_URL
        self._client: Optional[redis.Redis] = None
        self._prefix = config.CONFIG_PREFIX
        self._initialize_defaults()

    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _initialize_defaults(self) -> None:
        """Initialize default values in Redis if not present."""
        client = self._get_client()
        for key, value in self.DEFAULTS.items():
            redis_key = f"{self._prefix}{key}"
            if not client.exists(redis_key):
                self._set_value(key, value)
                logger.debug(f"Initialized {key} = {value}")

    def _set_value(self, key: str, value: Any) -> None:
        """Set a config value in Redis."""
        client = self._get_client()
        redis_key = f"{self._prefix}{key}"

        if isinstance(value, (list, dict)):
            client.set(redis_key, json.dumps(value))
        elif isinstance(value, bool):
            client.set(redis_key, "true" if value else "false")
        else:
            client.set(redis_key, str(value))

    def _get_value(self, key: str, value_type: type = str) -> Any:
        """Get a config value from Redis with type conversion."""
        client = self._get_client()
        redis_key = f"{self._prefix}{key}"
        raw_value = client.get(redis_key)

        if raw_value is None:
            return self.DEFAULTS.get(key)

        if value_type == bool:
            return raw_value.lower() == "true"
        elif value_type == float:
            return float(raw_value)
        elif value_type == int:
            return int(raw_value)
        elif value_type == list:
            return json.loads(raw_value)
        else:
            return raw_value

    # Getters for all config values
    @property
    def max_loss_per_trade_percent(self) -> float:
        return self._get_value("max_loss_per_trade_percent", float)

    @property
    def max_daily_trades(self) -> int:
        return self._get_value("max_daily_trades", int)

    @property
    def max_concurrent_positions(self) -> int:
        return self._get_value("max_concurrent_positions", int)

    @property
    def max_loss_per_day_percent(self) -> float:
        return self._get_value("max_loss_per_day_percent", float)

    @property
    def default_stop_loss_percent(self) -> float:
        return self._get_value("default_stop_loss_percent", float)

    @property
    def default_take_profit_percent(self) -> float:
        return self._get_value("default_take_profit_percent", float)

    @property
    def trailing_stop_enabled(self) -> bool:
        return self._get_value("trailing_stop_enabled", bool)

    @property
    def trailing_stop_activation_percent(self) -> float:
        return self._get_value("trailing_stop_activation_percent", float)

    @property
    def trailing_stop_distance_percent(self) -> float:
        return self._get_value("trailing_stop_distance_percent", float)

    @property
    def min_ai_confidence_score(self) -> float:
        return self._get_value("min_ai_confidence_score", float)

    @property
    def blacklist_tickers(self) -> List[str]:
        return self._get_value("blacklist_tickers", list)

    @property
    def whitelist_tickers(self) -> List[str]:
        return self._get_value("whitelist_tickers", list)

    @property
    def max_position_size_percent(self) -> float:
        return self._get_value("max_position_size_percent", float)

    @property
    def emergency_stop(self) -> bool:
        return self._get_value("emergency_stop", bool)

    @property
    def max_vix_level(self) -> float:
        return self._get_value("max_vix_level", float)

    @property
    def current_llm_model(self) -> str:
        return self._get_value("current_llm_model", str)

    @property
    def execute_orders(self) -> bool:
        """If False, simulates orders without sending to IBeam (dry run mode)."""
        return self._get_value("execute_orders", bool)

    # Setters for dynamic updates (Discord bot will use these)
    def set(self, key: str, value: Any) -> bool:
        """Set a config value.

        Args:
            key: Config key name
            value: New value

        Returns:
            True if successful
        """
        if key not in self.DEFAULTS:
            logger.warning(f"Unknown config key: {key}")
            return False

        self._set_value(key, value)
        logger.info(f"Config updated: {key} = {value}")
        return True

    def get_all(self) -> Dict[str, Any]:
        """Get all config values."""
        return {
            "max_loss_per_trade_percent": self.max_loss_per_trade_percent,
            "max_daily_trades": self.max_daily_trades,
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_loss_per_day_percent": self.max_loss_per_day_percent,
            "default_stop_loss_percent": self.default_stop_loss_percent,
            "default_take_profit_percent": self.default_take_profit_percent,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "trailing_stop_activation_percent": self.trailing_stop_activation_percent,
            "trailing_stop_distance_percent": self.trailing_stop_distance_percent,
            "min_ai_confidence_score": self.min_ai_confidence_score,
            "blacklist_tickers": self.blacklist_tickers,
            "whitelist_tickers": self.whitelist_tickers,
            "max_position_size_percent": self.max_position_size_percent,
            "emergency_stop": self.emergency_stop,
            "max_vix_level": self.max_vix_level,
            "current_llm_model": self.current_llm_model,
            "execute_orders": self.execute_orders,
        }

    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            self._client = None


# Singleton instance
trading_config = TradingConfig()