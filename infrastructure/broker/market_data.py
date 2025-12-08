"""Market data provider with IBKR + yfinance fallback.

Data Source Priority:
1. IBKR (if USE_IBKR_MARKET_DATA=true and connection healthy)
2. yfinance (fallback)

Set USE_IBKR_MARKET_DATA=true in .env when you have IBKR market data subscription.
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from infrastructure.broker.ibkr_client import IBKRBroker
from config.settings import config

logger = logging.getLogger(__name__)


# IBKR Market Data Field IDs
# See: https://interactivebrokers.github.io/tws-api/tick_types.html
IBKR_FIELDS = {
    "last_price": "31",      # Last traded price
    "bid": "84",             # Bid price
    "ask": "86",             # Ask price
    "high": "70",            # High price
    "low": "71",             # Low price
    "close": "7295",         # Prior close
    "volume": "7762",        # Volume
    "open": "7295",          # Open price (using prior close as fallback)
}


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
    """Market data with IBKR primary + yfinance fallback.
    
    Configuration:
        Set USE_IBKR_MARKET_DATA=true in environment to enable IBKR market data.
        Default is false (uses yfinance).
    """

    def __init__(
        self,
        broker: Optional[IBKRBroker] = None,
        force_ibkr: Optional[bool] = None,
    ):
        """Initialize market data provider.

        Args:
            broker: IBKR broker client
            force_ibkr: Override env setting. True=force IBKR, False=force yfinance, None=use env
        """
        self._broker = broker or IBKRBroker()
        self._ibkr_enabled = self._should_use_ibkr(force_ibkr)
        self._ibkr_healthy = False
        self._preflight_done = False
        
        if self._ibkr_enabled:
            self._check_ibkr_availability()
        else:
            logger.info("Using yfinance for market data (USE_IBKR_MARKET_DATA=false)")

    def _should_use_ibkr(self, force: Optional[bool]) -> bool:
        """Determine if IBKR should be used based on config."""
        if force is not None:
            return force
        
        # Use central config
        return config.USE_IBKR_MARKET_DATA

    def _check_ibkr_availability(self) -> None:
        """Check if IBKR market data is available."""
        try:
            self._ibkr_healthy = self._broker.check_health()
            if self._ibkr_healthy:
                logger.info("IBKR connection healthy - using IBKR for market data")
                self._do_preflight()
            else:
                logger.warning("IBKR connection unhealthy, falling back to yfinance")
        except Exception as e:
            self._ibkr_healthy = False
            logger.warning(f"IBKR check failed ({e}), falling back to yfinance")

    def _do_preflight(self) -> None:
        """Do IBKR preflight request (required before market data)."""
        if self._preflight_done:
            return
            
        try:
            # Call accounts endpoint - required before market data
            self._broker.get_accounts()
            self._preflight_done = True
            logger.debug("IBKR preflight completed")
        except Exception as e:
            logger.warning(f"IBKR preflight failed: {e}")

    @property
    def using_ibkr(self) -> bool:
        """Check if currently using IBKR for market data."""
        return self._ibkr_enabled and self._ibkr_healthy

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Current price or None
        """
        # Try IBKR first if enabled and healthy
        if self.using_ibkr:
            price = self._get_price_ibkr(symbol)
            if price is not None:
                return price
            logger.debug(f"IBKR price fetch failed for {symbol}, trying yfinance")

        # Fallback to yfinance
        return self._get_price_yfinance(symbol)

    def _get_price_ibkr(self, symbol: str) -> Optional[float]:
        """Get price from IBKR live market data snapshot."""
        try:
            # Search for contract to get conid
            contract = self._broker.search_contract(symbol)
            if not contract:
                logger.debug(f"Contract not found for {symbol}")
                return None
            
            conid = str(contract.get("conid"))
            
            # Get live market data snapshot
            # Fields: 31=last price, 84=bid, 86=ask
            client = self._broker._get_client()
            
            # First request may return empty - IBKR requires "warming up"
            for attempt in range(2):
                result = client.live_marketdata_snapshot(
                    conids=[conid],
                    fields=[IBKR_FIELDS["last_price"], IBKR_FIELDS["bid"], IBKR_FIELDS["ask"]]
                )
                
                if result.data and len(result.data) > 0:
                    snapshot = result.data[0]
                    
                    # Try last price first, then mid of bid/ask
                    last_price = snapshot.get(IBKR_FIELDS["last_price"])
                    if last_price and str(last_price) not in ("", "N/A", "0"):
                        price = float(last_price)
                        logger.debug(f"{symbol} price (IBKR): ${price:.2f}")
                        return price
                    
                    # Try bid/ask midpoint
                    bid = snapshot.get(IBKR_FIELDS["bid"])
                    ask = snapshot.get(IBKR_FIELDS["ask"])
                    if bid and ask:
                        try:
                            mid = (float(bid) + float(ask)) / 2
                            logger.debug(f"{symbol} price (IBKR mid): ${mid:.2f}")
                            return mid
                        except (ValueError, TypeError):
                            pass
                
                # Wait a bit before retry (IBKR needs time to prepare data)
                if attempt == 0:
                    time.sleep(0.3)
            
            logger.debug(f"No valid price data from IBKR for {symbol}")
            return None
            
        except Exception as e:
            logger.debug(f"IBKR price fetch failed for {symbol}: {e}")
            return None

    def _get_price_yfinance(self, symbol: str) -> Optional[float]:
        """Get price from yfinance."""
        try:
            # Index symbols need ^ prefix in yfinance
            yf_symbol = symbol
            if symbol.upper() in ['SPX', 'NDX', 'RUT', 'VIX', 'DJX']:
                yf_symbol = f"^{symbol.upper()}"
            
            ticker = yf.Ticker(yf_symbol)
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

        Note: VIX is always from yfinance (free, no subscription needed)

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
        # Try IBKR first
        if self.using_ibkr:
            volume = self._get_volume_ibkr(symbol)
            if volume is not None:
                return volume
        
        # Fallback to yfinance
        return self._get_volume_yfinance(symbol)

    def _get_volume_ibkr(self, symbol: str) -> Optional[int]:
        """Get volume from IBKR."""
        try:
            contract = self._broker.search_contract(symbol)
            if not contract:
                return None
            
            conid = str(contract.get("conid"))
            client = self._broker._get_client()
            
            result = client.live_marketdata_snapshot(
                conids=[conid],
                fields=[IBKR_FIELDS["volume"]]
            )
            
            if result.data and len(result.data) > 0:
                snapshot = result.data[0]
                volume = snapshot.get(IBKR_FIELDS["volume"])
                if volume and str(volume) not in ("", "N/A"):
                    return int(float(volume))
            
            return None
        except Exception as e:
            logger.debug(f"IBKR volume fetch failed for {symbol}: {e}")
            return None

    def _get_volume_yfinance(self, symbol: str) -> Optional[int]:
        """Get volume from yfinance."""
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

        Note: Always uses yfinance for historical data.

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
            "source": "ibkr" if self.using_ibkr else "yfinance",
            "timestamp": datetime.now().isoformat(),
        }

    def get_option_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get option chain for a symbol.

        Note: Option chains from IBKR require more complex setup.
        Currently using yfinance for simplicity.
        TODO: Implement IBKR option chain when needed.

        Args:
            symbol: Underlying symbol
            expiry: Optional expiry filter

        Returns:
            Option chain data
        """
        # For now, always use yfinance for option chains
        # IBKR option chain requires secdef lookups which is more complex
        return self._get_option_chain_yfinance(symbol, expiry)

    def _get_option_chain_yfinance(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get option chain from yfinance.
        
        Optimized to return only relevant data:
        - Only strikes within ±10% of current price
        - Limited available_expiries to nearest 5 (reduce payload)
        """
        try:
            # Index symbols need ^ prefix in yfinance
            yf_symbol = symbol
            if symbol.upper() in ['SPX', 'NDX', 'RUT', 'VIX', 'DJX']:
                yf_symbol = f"^{symbol.upper()}"
            
            ticker = yf.Ticker(yf_symbol)

            # Get available expirations
            expirations = ticker.options

            if not expirations:
                return {"error": "No options available"}

            # Use specified expiry or nearest
            target_expiry = expiry if expiry in expirations else expirations[0]

            # Get option chain
            chain = ticker.option_chain(target_expiry)
            
            # Get current price to filter relevant strikes
            current_price = self.get_current_price(symbol)
            
            # Filter strikes to ±10% of current price (reduces data significantly)
            strike_min = current_price * 0.90 if current_price else 0
            strike_max = current_price * 1.10 if current_price else float('inf')

            # Convert DataFrames to dicts WITH TIMESTAMP CONVERSION
            # Filter to relevant strikes only
            calls_data = []
            puts_data = []

            if not chain.calls.empty:
                # Filter calls by strike range
                filtered_calls = chain.calls[
                    (chain.calls['strike'] >= strike_min) & 
                    (chain.calls['strike'] <= strike_max)
                ]
                # Also filter out options with 0 bid AND 0 ask (illiquid/no quotes)
                if 'bid' in filtered_calls.columns and 'ask' in filtered_calls.columns:
                    filtered_calls = filtered_calls[
                        (filtered_calls['bid'] > 0) | (filtered_calls['ask'] > 0)
                    ]
                calls_data = filtered_calls.to_dict(orient="records")
                calls_data = convert_timestamps(calls_data)

            if not chain.puts.empty:
                # Filter puts by strike range
                filtered_puts = chain.puts[
                    (chain.puts['strike'] >= strike_min) & 
                    (chain.puts['strike'] <= strike_max)
                ]
                # Also filter out options with 0 bid AND 0 ask (illiquid/no quotes)
                if 'bid' in filtered_puts.columns and 'ask' in filtered_puts.columns:
                    filtered_puts = filtered_puts[
                        (filtered_puts['bid'] > 0) | (filtered_puts['ask'] > 0)
                    ]
                puts_data = filtered_puts.to_dict(orient="records")
                puts_data = convert_timestamps(puts_data)

            # Only return nearest 5 expiries to reduce payload
            nearby_expiries = list(expirations)[:5]
            
            # Add warning if no liquid options found
            warning = None
            if not calls_data and not puts_data:
                warning = "No liquid options found (all have bid=0 and ask=0). Market may be closed or options illiquid."

            return {
                "symbol": symbol,
                "expiry": target_expiry,
                "available_expiries": nearby_expiries,
                "current_price": current_price,
                "strike_range": f"{strike_min:.2f} - {strike_max:.2f}",
                "calls": calls_data,
                "puts": puts_data,
                "calls_count": len(calls_data),
                "puts_count": len(puts_data),
                "warning": warning,
                "source": "yfinance",
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

        Note: Historical data always from yfinance (free, comprehensive)

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
                "source": "yfinance",
            }

        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {e}")
            return {"error": str(e)}

    def get_data_source_info(self) -> Dict[str, Any]:
        """Get information about current data source configuration."""
        return {
            "ibkr_enabled": self._ibkr_enabled,
            "ibkr_healthy": self._ibkr_healthy,
            "using_ibkr": self.using_ibkr,
            "primary_source": "ibkr" if self.using_ibkr else "yfinance",
            "config_setting": config.USE_IBKR_MARKET_DATA,
        }
