"""Market data tools for AI - FIXED VERSION with proper NYSE hours."""

from datetime import datetime, date
from typing import Any, Dict, List, Optional
import pytz

from infrastructure.broker.market_data import MarketDataProvider


# NYSE Holiday Calendar 2024-2025
# Source: https://www.nyse.com/markets/hours-calendars
NYSE_HOLIDAYS_2024 = {
    date(2024, 1, 1),    # New Year's Day
    date(2024, 1, 15),   # Martin Luther King Jr. Day
    date(2024, 2, 19),   # Presidents' Day
    date(2024, 3, 29),   # Good Friday
    date(2024, 5, 27),   # Memorial Day
    date(2024, 6, 19),   # Juneteenth
    date(2024, 7, 4),    # Independence Day
    date(2024, 9, 2),    # Labor Day
    date(2024, 11, 28),  # Thanksgiving Day
    date(2024, 12, 25),  # Christmas Day
}

NYSE_HOLIDAYS_2025 = {
    date(2025, 1, 1),    # New Year's Day
    date(2025, 1, 20),   # Martin Luther King Jr. Day
    date(2025, 2, 17),   # Presidents' Day
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 26),   # Memorial Day
    date(2025, 6, 19),   # Juneteenth
    date(2025, 7, 4),    # Independence Day
    date(2025, 9, 1),    # Labor Day
    date(2025, 11, 27),  # Thanksgiving Day
    date(2025, 12, 25),  # Christmas Day
}

NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # Martin Luther King Jr. Day
    date(2026, 2, 16),   # Presidents' Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed - July 4 is Saturday)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving Day
    date(2026, 12, 25),  # Christmas Day
}

NYSE_HOLIDAYS = NYSE_HOLIDAYS_2024 | NYSE_HOLIDAYS_2025 | NYSE_HOLIDAYS_2026

# Early close days (1:00 PM ET)
NYSE_EARLY_CLOSE_2024 = {
    date(2024, 7, 3),    # Day before Independence Day
    date(2024, 11, 29),  # Day after Thanksgiving (Black Friday)
    date(2024, 12, 24),  # Christmas Eve
}

NYSE_EARLY_CLOSE_2025 = {
    date(2025, 7, 3),    # Day before Independence Day
    date(2025, 11, 28),  # Day after Thanksgiving (Black Friday)
    date(2025, 12, 24),  # Christmas Eve
}

NYSE_EARLY_CLOSE_2026 = {
    date(2026, 11, 27),  # Day after Thanksgiving (Black Friday)
    date(2026, 12, 24),  # Christmas Eve
}

NYSE_EARLY_CLOSE = NYSE_EARLY_CLOSE_2024 | NYSE_EARLY_CLOSE_2025 | NYSE_EARLY_CLOSE_2026


def is_nyse_open(dt: datetime) -> Dict[str, Any]:
    """Check if NYSE is open at the given datetime.

    Args:
        dt: Datetime in US/Eastern timezone

    Returns:
        Dict with is_open, reason, next_open, close_time
    """
    current_date = dt.date()
    current_time = dt.time()

    # Check if weekend
    if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return {
            "is_open": False,
            "reason": "weekend",
            "day_of_week": dt.strftime("%A"),
        }

    # Check if holiday
    if current_date in NYSE_HOLIDAYS:
        return {
            "is_open": False,
            "reason": "holiday",
            "holiday": _get_holiday_name(current_date),
        }

    # Regular hours: 9:30 AM - 4:00 PM ET
    market_open_time = dt.replace(hour=9, minute=30, second=0, microsecond=0).time()

    # Check for early close
    if current_date in NYSE_EARLY_CLOSE:
        market_close_time = dt.replace(hour=13, minute=0, second=0, microsecond=0).time()
        close_reason = "early_close"
    else:
        market_close_time = dt.replace(hour=16, minute=0, second=0, microsecond=0).time()
        close_reason = "regular_close"

    # Check time
    if current_time < market_open_time:
        return {
            "is_open": False,
            "reason": "pre_market",
            "opens_at": "09:30 ET",
            "closes_at": "13:00 ET" if current_date in NYSE_EARLY_CLOSE else "16:00 ET",
        }
    elif current_time > market_close_time:
        return {
            "is_open": False,
            "reason": "after_hours",
            "closed_at": "13:00 ET" if current_date in NYSE_EARLY_CLOSE else "16:00 ET",
        }
    else:
        return {
            "is_open": True,
            "reason": "regular_hours" if close_reason == "regular_close" else "early_close_day",
            "closes_at": "13:00 ET" if current_date in NYSE_EARLY_CLOSE else "16:00 ET",
        }


def _get_holiday_name(d: date) -> str:
    """Get holiday name for a date."""
    holiday_names = {
        # 2024
        date(2024, 1, 1): "New Year's Day",
        date(2024, 1, 15): "Martin Luther King Jr. Day",
        date(2024, 2, 19): "Presidents' Day",
        date(2024, 3, 29): "Good Friday",
        date(2024, 5, 27): "Memorial Day",
        date(2024, 6, 19): "Juneteenth",
        date(2024, 7, 4): "Independence Day",
        date(2024, 9, 2): "Labor Day",
        date(2024, 11, 28): "Thanksgiving Day",
        date(2024, 12, 25): "Christmas Day",
        # 2025
        date(2025, 1, 1): "New Year's Day",
        date(2025, 1, 20): "Martin Luther King Jr. Day",
        date(2025, 2, 17): "Presidents' Day",
        date(2025, 4, 18): "Good Friday",
        date(2025, 5, 26): "Memorial Day",
        date(2025, 6, 19): "Juneteenth",
        date(2025, 7, 4): "Independence Day",
        date(2025, 9, 1): "Labor Day",
        date(2025, 11, 27): "Thanksgiving Day",
        date(2025, 12, 25): "Christmas Day",
        # 2026
        date(2026, 1, 1): "New Year's Day",
        date(2026, 1, 19): "Martin Luther King Jr. Day",
        date(2026, 2, 16): "Presidents' Day",
        date(2026, 4, 3): "Good Friday",
        date(2026, 5, 25): "Memorial Day",
        date(2026, 6, 19): "Juneteenth",
        date(2026, 7, 3): "Independence Day (observed)",
        date(2026, 9, 7): "Labor Day",
        date(2026, 11, 26): "Thanksgiving Day",
        date(2026, 12, 25): "Christmas Day",
    }
    return holiday_names.get(d, "Unknown Holiday")


class MarketTools:
    """Market data tools for AI function calling."""

    def __init__(self, market_data: Optional[MarketDataProvider] = None):
        """Initialize market tools."""
        self._market_data = market_data or MarketDataProvider()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current trading time in EST/ET timezone and NYSE market status (open/closed, including holidays and early close days)",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ticker_price",
                    "description": "Get the current price for a ticker symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol (e.g., SPY, QQQ)",
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_volume",
                    "description": "Get the current trading volume for a ticker",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol",
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_volatility",
                    "description": "Get the historical volatility for a ticker",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The ticker symbol",
                            },
                            "period": {
                                "type": "integer",
                                "description": "Lookback period in days (default: 20)",
                                "default": 20,
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vix",
                    "description": "Get the current VIX (volatility index) level",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_option_chain",
                    "description": "Get the option chain for a symbol",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "The underlying ticker symbol",
                            },
                            "expiry": {
                                "type": "string",
                                "description": "Expiry date (YYYY-MM-DD format, optional)",
                            },
                        },
                        "required": ["symbol"],
                    },
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions."""
        return {
            "get_current_time": self.get_current_time,
            "get_ticker_price": self.get_ticker_price,
            "get_volume": self.get_volume,
            "get_volatility": self.get_volatility,
            "get_vix": self.get_vix,
            "get_option_chain": self.get_option_chain,
        }

    def get_current_time(self) -> Dict[str, Any]:
        """Get current trading time in EST with accurate NYSE market status.

        Returns:
            Time information including NYSE open/closed status with reason
        """
        est = pytz.timezone("US/Eastern")
        now = datetime.now(est)

        # Get detailed market status
        market_status = is_nyse_open(now)

        return {
            "timestamp": now.isoformat(),
            "time_est": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "day_of_week": now.strftime("%A"),
            "timezone": "US/Eastern (ET)",
            # Main status
            "is_market_open": market_status["is_open"],
            "market_status": "open" if market_status["is_open"] else "closed",
            "status_reason": market_status["reason"],
            # Additional details from market_status
            **{k: v for k, v in market_status.items() if k not in ["is_open", "reason"]},
        }

    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker price."""
        price = self._market_data.get_current_price(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "price": price,
            "currency": "USD",
            "timestamp": datetime.now().isoformat(),
            "source": "market_data",
        }

    def get_volume(self, symbol: str) -> Dict[str, Any]:
        """Get current volume."""
        volume = self._market_data.get_volume(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "volume": volume,
            "timestamp": datetime.now().isoformat(),
        }

    def get_volatility(self, symbol: str, period: int = 20) -> Dict[str, Any]:
        """Get historical volatility."""
        volatility = self._market_data.get_volatility(symbol.upper(), period)

        return {
            "symbol": symbol.upper(),
            "volatility": volatility,
            "period_days": period,
            "annualized": True,
            "timestamp": datetime.now().isoformat(),
        }

    def get_vix(self) -> Dict[str, Any]:
        """Get current VIX."""
        vix = self._market_data.get_vix()

        return {
            "vix": vix,
            "timestamp": datetime.now().isoformat(),
        }

    def get_option_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get option chain."""
        return self._market_data.get_option_chain(symbol.upper(), expiry)
