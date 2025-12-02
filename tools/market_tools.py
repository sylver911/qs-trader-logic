"""Market data tools for AI."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import pytz

from infrastructure.broker.market_data import MarketDataProvider


class MarketTools:
    """Market data tools for AI function calling."""

    def __init__(self, market_data: Optional[MarketDataProvider] = None):
        """Initialize market tools.

        Args:
            market_data: Market data provider
        """
        self._market_data = market_data or MarketDataProvider()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions.

        Returns:
            List of tool definitions
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get the current trading time in EST timezone",
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
        """Get tool handler functions.

        Returns:
            Map of function names to handlers
        """
        return {
            "get_current_time": self.get_current_time,
            "get_ticker_price": self.get_ticker_price,
            "get_volume": self.get_volume,
            "get_volatility": self.get_volatility,
            "get_vix": self.get_vix,
            "get_option_chain": self.get_option_chain,
        }

    def get_current_time(self) -> Dict[str, Any]:
        """Get current trading time in EST.

        Returns:
            Time information
        """
        est = pytz.timezone("US/Eastern")
        now = datetime.now(est)

        # Check if market is open (simplified)
        is_weekday = now.weekday() < 5
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        is_market_hours = market_open <= now <= market_close

        return {
            "timestamp": now.isoformat(),
            "time_est": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "day_of_week": now.strftime("%A"),
            "is_weekday": is_weekday,
            "is_market_hours": is_weekday and is_market_hours,
            "market_status": "open" if (is_weekday and is_market_hours) else "closed",
        }

    def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """Get current ticker price.

        Args:
            symbol: Ticker symbol

        Returns:
            Price data
        """
        price = self._market_data.get_current_price(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "price": price,
            "currency": "USD",
            "timestamp": datetime.now().isoformat(),
            "source": "market_data",
        }

    def get_volume(self, symbol: str) -> Dict[str, Any]:
        """Get current volume.

        Args:
            symbol: Ticker symbol

        Returns:
            Volume data
        """
        volume = self._market_data.get_volume(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "volume": volume,
            "timestamp": datetime.now().isoformat(),
        }

    def get_volatility(self, symbol: str, period: int = 20) -> Dict[str, Any]:
        """Get historical volatility.

        Args:
            symbol: Ticker symbol
            period: Lookback period

        Returns:
            Volatility data
        """
        volatility = self._market_data.get_volatility(symbol.upper(), period)

        return {
            "symbol": symbol.upper(),
            "volatility": volatility,
            "period_days": period,
            "annualized": True,
            "timestamp": datetime.now().isoformat(),
        }

    def get_vix(self) -> Dict[str, Any]:
        """Get current VIX.

        Returns:
            VIX data
        """
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
        """Get option chain.

        Args:
            symbol: Underlying symbol
            expiry: Optional expiry date

        Returns:
            Option chain data
        """
        return self._market_data.get_option_chain(symbol.upper(), expiry)
