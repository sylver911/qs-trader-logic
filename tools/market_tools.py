"""Market data tools for AI - QS Optimized Version.

Simplified tool set focused on execution validation:
- Time/market status
- Current prices
- Option chain (for current option prices)
- VIX (already checked in preconditions, but available if needed)
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional
import pytz

from infrastructure.broker.market_data import MarketDataProvider


# NYSE Holiday Calendar 2024-2026
NYSE_HOLIDAYS = {
    # 2024
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19), date(2024, 3, 29),
    date(2024, 5, 27), date(2024, 6, 19), date(2024, 7, 4), date(2024, 9, 2),
    date(2024, 11, 28), date(2024, 12, 25),
    # 2025
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}

# Early close days (1:00 PM ET)
NYSE_EARLY_CLOSE = {
    date(2024, 7, 3), date(2024, 11, 29), date(2024, 12, 24),
    date(2025, 7, 3), date(2025, 11, 28), date(2025, 12, 24),
    date(2026, 11, 27), date(2026, 12, 24),
}


def is_nyse_open(dt: datetime) -> Dict[str, Any]:
    """Check if NYSE is open at the given datetime."""
    current_date = dt.date()
    current_time = dt.time()

    if dt.weekday() >= 5:
        return {"is_open": False, "reason": "weekend", "day_of_week": dt.strftime("%A")}

    if current_date in NYSE_HOLIDAYS:
        return {"is_open": False, "reason": "holiday"}

    market_open_time = dt.replace(hour=9, minute=30, second=0, microsecond=0).time()
    
    if current_date in NYSE_EARLY_CLOSE:
        market_close_time = dt.replace(hour=13, minute=0, second=0, microsecond=0).time()
    else:
        market_close_time = dt.replace(hour=16, minute=0, second=0, microsecond=0).time()

    if current_time < market_open_time:
        return {"is_open": False, "reason": "pre_market", "opens_at": "09:30 ET"}
    elif current_time > market_close_time:
        return {"is_open": False, "reason": "after_hours"}
    else:
        return {"is_open": True, "reason": "market_open", "closes_at": "13:00 ET" if current_date in NYSE_EARLY_CLOSE else "16:00 ET"}


class MarketTools:
    """Market data tools for AI function calling - QS Optimized."""

    def __init__(self, market_data: Optional[MarketDataProvider] = None):
        """Initialize market tools."""
        self._market_data = market_data or MarketDataProvider()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions.
        
        QS Optimized: Only essential tools for execution validation.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get current time in EST and NYSE market status (open/closed). CALL THIS FIRST to check if trading is possible.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ticker_price",
                    "description": "Get current stock price for the underlying ticker (e.g., SPY, QQQ). Use this to compare current underlying price to signal's strike.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Ticker symbol (e.g., SPY, QQQ)"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_option_chain",
                    "description": "Get option chain with current option prices. ESSENTIAL for calculating current R:R ratio. Returns calls and puts with bid/ask/last prices.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "Underlying ticker (e.g., SPY)"},
                            "expiry": {"type": "string", "description": "Expiry date YYYY-MM-DD format"},
                        },
                        "required": ["symbol"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vix",
                    "description": "Get current VIX level. Note: VIX is already checked in preconditions, use only if you need the exact value for reasoning.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions."""
        return {
            "get_current_time": self.get_current_time,
            "get_ticker_price": self.get_ticker_price,
            "get_option_chain": self.get_option_chain,
            "get_vix": self.get_vix,
        }

    def get_current_time(self) -> Dict[str, Any]:
        """Get current trading time in EST with NYSE market status."""
        est = pytz.timezone("US/Eastern")
        now = datetime.now(est)
        market_status = is_nyse_open(now)

        return {
            "timestamp": now.isoformat(),
            "time_est": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "day_of_week": now.strftime("%A"),
            "timezone": "US/Eastern (ET)",
            "is_market_open": market_status["is_open"],
            "market_status": "open" if market_status["is_open"] else "closed",
            "status_reason": market_status["reason"],
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
        }

    def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> Dict[str, Any]:
        """Get option chain with current prices."""
        return self._market_data.get_option_chain(symbol.upper(), expiry)

    def get_vix(self) -> Dict[str, Any]:
        """Get current VIX."""
        vix = self._market_data.get_vix()
        return {"vix": vix, "timestamp": datetime.now().isoformat()}
