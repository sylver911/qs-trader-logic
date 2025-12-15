"""Option chain prefetch.

Fetches option chain data for the signal's ticker.

Jinja2 template usage:
    {{ option_chain.symbol }}              -> "SPY"
    {{ option_chain.current_price }}       -> 680.50
    {{ option_chain.expiry }}              -> "2025-12-15"
    {{ option_chain.available_expiries }}  -> ["2025-12-15", "2025-12-16", ...]

    Calls:
    {% for call in option_chain.calls[:5] %}
        Strike ${{ call.strike }}: ${{ call.bid }}/${{ call.ask }} ({{ "ITM" if call.in_the_money else "OTM" }})
    {% endfor %}

    Puts:
    {% for put in option_chain.puts[:5] %}
        Strike ${{ put.strike }}: ${{ put.bid }}/${{ put.ask }}
    {% endfor %}

    Find specific strike:
    {% for call in option_chain.calls if call.strike == 680 %}
        Target call: ${{ call.bid }}/${{ call.ask }}
    {% endfor %}
"""

import logging
from typing import Any, Dict, List, Optional

from domain.prefetches.base import Prefetch, PrefetchResult

logger = logging.getLogger(__name__)


class OptionChainPrefetch(Prefetch):
    """Prefetch option chain for the signal's ticker.

    Template key: option_chain
    """

    name = "option_chain"
    key = "option_chain"
    description = "Option chain with calls and puts for signal ticker"
    requires_ticker = True
    requires_broker = False  # Uses yfinance fallback

    def fetch(self, signal, context: Dict[str, Any]) -> PrefetchResult:
        """Fetch option chain data."""
        try:
            market_data = context.get("market_data")
            if not market_data:
                return PrefetchResult.from_error("No market_data provider in context")

            ticker = signal.ticker
            if not ticker:
                return PrefetchResult.from_error("No ticker in signal")

            # Get option chain (uses signal expiry if available)
            chain_data = market_data.get_option_chain(
                ticker.upper(),
                expiry=signal.expiry,
            )

            if not chain_data:
                return PrefetchResult.from_error(f"No option chain data for {ticker}")

            # Normalize the data for template use
            calls = self._normalize_options(chain_data.get("calls", []))
            puts = self._normalize_options(chain_data.get("puts", []))

            data = {
                "symbol": chain_data.get("symbol", ticker.upper()),
                "current_price": chain_data.get("current_price", 0),
                "expiry": chain_data.get("expiry"),
                "available_expiries": chain_data.get("available_expiries", []),
                "calls": calls,
                "puts": puts,
                "calls_count": len(calls),
                "puts_count": len(puts),
            }

            return PrefetchResult.from_data(data)

        except Exception as e:
            logger.error(f"Option chain prefetch error: {e}")
            return PrefetchResult.from_error(str(e))

    def _normalize_options(self, options: List[Dict]) -> List[Dict]:
        """Normalize option data for consistent template access."""
        normalized = []
        for opt in options:
            normalized.append({
                "strike": opt.get("strike", 0),
                "bid": opt.get("bid", 0),
                "ask": opt.get("ask", 0),
                "last": opt.get("lastPrice", opt.get("last", 0)),
                "volume": opt.get("volume", 0),
                "open_interest": opt.get("openInterest", opt.get("open_interest", 0)),
                "implied_volatility": opt.get("impliedVolatility", opt.get("iv", 0)),
                "in_the_money": opt.get("inTheMoney", opt.get("in_the_money", False)),
                "mid": (opt.get("bid", 0) + opt.get("ask", 0)) / 2 if opt.get("bid") and opt.get("ask") else 0,
            })
        return normalized
