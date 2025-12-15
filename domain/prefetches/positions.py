"""Positions prefetch.

Fetches current open positions.

Jinja2 template usage:
    {{ positions.count }}          -> 3
    {{ positions.tickers }}        -> ["SPY", "QQQ", "AAPL"]
    {{ positions.has_positions }}  -> True/False

    Iterate positions:
    {% for pos in positions.items %}
        {{ pos.symbol }}: {{ pos.quantity }} @ ${{ pos.avg_cost }} (P&L: ${{ pos.unrealized_pnl }})
    {% endfor %}

    Check for specific ticker:
    {% if signal.ticker in positions.tickers %}
        Already have position in {{ signal.ticker }}!
    {% endif %}

    Total P&L:
    {{ positions.total_unrealized_pnl }}
"""

import logging
from typing import Any, Dict, List

from domain.prefetches.base import Prefetch, PrefetchResult

logger = logging.getLogger(__name__)


class PositionsPrefetch(Prefetch):
    """Prefetch current open positions.

    Template key: positions
    """

    name = "positions"
    key = "positions"
    description = "Current open positions"
    requires_ticker = False
    requires_broker = True

    def fetch(self, signal, context: Dict[str, Any]) -> PrefetchResult:
        """Fetch current positions."""
        try:
            broker = context.get("broker")
            trading_config = context.get("trading_config")

            # In dry run mode, return empty positions
            if trading_config and not trading_config.execute_orders:
                data = {
                    "count": 0,
                    "tickers": [],
                    "items": [],
                    "has_positions": False,
                    "total_unrealized_pnl": 0,
                    "total_market_value": 0,
                    "is_simulated": True,
                }
                return PrefetchResult.from_data(data)

            if not broker:
                return PrefetchResult.from_error("No broker in context")

            # Get real positions
            positions_data = broker.get_positions()

            if positions_data is None:
                return PrefetchResult.from_error("Failed to get positions")

            # Normalize for template use
            items = self._normalize_positions(positions_data)
            tickers = list(set(p["ticker"] for p in items if p.get("ticker")))

            data = {
                "count": len(items),
                "tickers": tickers,
                "items": items,
                "has_positions": len(items) > 0,
                "total_unrealized_pnl": sum(p.get("unrealized_pnl", 0) for p in items),
                "total_market_value": sum(p.get("market_value", 0) for p in items),
                "is_simulated": False,
            }

            return PrefetchResult.from_data(data)

        except Exception as e:
            logger.error(f"Positions prefetch error: {e}")
            return PrefetchResult.from_error(str(e))

    def _normalize_positions(self, positions: Any) -> List[Dict]:
        """Normalize position data for template access."""
        if not positions:
            return []

        # Handle different response formats
        if isinstance(positions, dict):
            positions = positions.get("positions", positions.get("items", []))

        if not isinstance(positions, list):
            return []

        normalized = []
        for pos in positions:
            # Extract ticker from symbol (handle option symbols)
            symbol = pos.get("symbol", pos.get("contractDesc", ""))
            ticker = symbol.split()[0] if symbol else ""

            normalized.append({
                "symbol": symbol,
                "ticker": ticker,
                "conid": pos.get("conid", ""),
                "quantity": pos.get("quantity", pos.get("position", 0)),
                "avg_cost": pos.get("avg_cost", pos.get("avgCost", pos.get("avgPrice", 0))),
                "market_value": pos.get("market_value", pos.get("mktValue", 0)),
                "unrealized_pnl": pos.get("unrealized_pnl", pos.get("unrealizedPnl", 0)),
                "realized_pnl": pos.get("realized_pnl", pos.get("realizedPnl", 0)),
                "currency": pos.get("currency", "USD"),
            })

        return normalized
