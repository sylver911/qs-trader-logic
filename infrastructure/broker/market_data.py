"""Market data provider with IBKR + yfinance fallback."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import yfinance as yf

from infrastructure.broker.ibkr_client import IBKRBroker

logger = logging.getLogger(__name__)


def convert_timestamps(obj: Any) -> Any:
    """Recursively convert pandas Timestamps to ISO strings.

    Args:
        obj: Object to convert

    Returns:
        Object with timestamps converted to strings
    """
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: convert_timestamps(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_timestamps(item) for item in obj]
    elif hasattr(obj, 'item'):  # numpy types
        return obj.item()
    return obj


class MarketDataProvider:
    """Market data with IBKR primary + yfinance fallback."""

    def __init__(self, broker: Optional[IBKRBroker] = None):
        """Initialize market data provider.

        Args:
            broker: IBKR broker client
        """
        self._broker = broker or IBKRBroker()
        self._use_ibkr = False
        self._check_ibkr_availability()

    def _check_ibkr_availability(self) -> None:
        """Check if IBKR market data is available."""
        try:
            self._use_ibkr = self._broker.check_health()
            if self._use_ibkr:
                logger.info("Using IBKR for market data")
            else:
                logger.info("IBKR unavailable, using yfinance fallback")
        except Exception:
            self._use_ibkr = False
            logger.info("IBKR check failed, using yfinance fallback")

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Current price or None
        """
        # Try IBKR first
        if self._use_ibkr:
            price = self._get_price_ibkr(symbol)
            if price:
                return price

        # Fallback to yfinance
        return self._get_price_yfinance(symbol)

    def _get_price_ibkr(self, symbol: str) -> Optional[float]:
        """Get price from IBKR."""
        try:
            contract = self._broker.search_contract(symbol)
            if contract:
                conid = contract.get("conid")
                # Would need to call live_marketdata_snapshot here
                # For now, fall back to yfinance
                logger.debug(f"IBKR contract found: {conid}")
            return None
        except Exception as e:
            logger.debug(f"IBKR price fetch failed: {e}")
            return None

    def _get_price_yfinance(self, symbol: str) -> Optional[float]:
        """Get price from yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")

            if data.empty:
                logger.warning(f"No data for {symbol}")
                return None

            price = float(data["Close"].iloc[-1])
            logger.debug(f"{symbol} price (yfinance): ${price:.2f}")
            return price

        except Exception as e:
            logger.error(f"yfinance price fetch failed for {symbol}: {e}")
            return None

    def get_vix(self) -> Optional[float]:
        """Get current VIX level.

        Returns:
            VIX value or None
        """
        try:
            vix = yf.Ticker("^VIX")
            data = vix.history(period="1d")

            if data.empty:
                return None

            value = float(data["Close"].iloc[-1])
            logger.debug(f"VIX: {value:.2f}")
            return value

        except Exception as e:
            logger.error(f"Failed to get VIX: {e}")
            return None

    def get_volume(self, symbol: str) -> Optional[int]:
        """Get current volume for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Volume or None
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")

            if data.empty:
                return None

            volume = int(data["Volume"].iloc[-1])
            logger.debug(f"{symbol} volume: {volume:,}")
            return volume

        except Exception as e:
            logger.error(f"Failed to get volume for {symbol}: {e}")
            return None

    def get_volatility(self, symbol: str, period: int = 20) -> Optional[float]:
        """Get historical volatility for a symbol.

        Args:
            symbol: Ticker symbol
            period: Lookback period in days

        Returns:
            Annualized volatility or None
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=f"{period + 5}d")

            if len(data) < period:
                return None

            # Calculate daily returns
            returns = data["Close"].pct_change().dropna()

            # Annualized volatility
            volatility = float(returns.std() * (252 ** 0.5))
            logger.debug(f"{symbol} volatility: {volatility:.2%}")
            return volatility

        except Exception as e:
            logger.error(f"Failed to get volatility for {symbol}: {e}")
            return None

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive market data for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Market data dictionary
        """
        return {
            "symbol": symbol,
            "price": self.get_current_price(symbol),
            "volume": self.get_volume(symbol),
            "volatility": self.get_volatility(symbol),
            "vix": self.get_vix(),
            "timestamp": datetime.now().isoformat(),
        }

    def get_option_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get option chain for a symbol.

        Args:
            symbol: Underlying symbol
            expiry: Optional expiry filter

        Returns:
            Option chain data
        """
        try:
            ticker = yf.Ticker(symbol)

            # Get available expirations
            expirations = ticker.options

            if not expirations:
                return {"error": "No options available"}

            # Use specified expiry or nearest
            target_expiry = expiry if expiry in expirations else expirations[0]

            # Get option chain
            chain = ticker.option_chain(target_expiry)

            # Convert DataFrames to dicts WITH TIMESTAMP CONVERSION
            calls_data = []
            puts_data = []

            if not chain.calls.empty:
                calls_data = chain.calls.to_dict(orient="records")
                calls_data = convert_timestamps(calls_data)

            if not chain.puts.empty:
                puts_data = chain.puts.to_dict(orient="records")
                puts_data = convert_timestamps(puts_data)

            return {
                "symbol": symbol,
                "expiry": target_expiry,
                "available_expiries": list(expirations),
                "calls": calls_data,
                "puts": puts_data,
            }

        except Exception as e:
            logger.error(f"Failed to get option chain for {symbol}: {e}")
            return {"error": str(e)}

    def get_historical_data(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """Get historical price data.

        Args:
            symbol: Ticker symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

        Returns:
            Historical data dictionary
        """
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)

            if data.empty:
                return {"error": f"No historical data for {symbol}"}

            # Convert to list of records WITH TIMESTAMP CONVERSION
            records = []
            for idx, row in data.iterrows():
                record = {
                    "date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                }
                records.append(record)

            return {
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "data": records,
            }

        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            return {"error": str(e)}