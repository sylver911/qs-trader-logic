"""Portfolio tools for AI - QS Optimized Version.

Simplified tool set for execution validation:
- Account summary (cash available)
- Positions (current count, check for duplicates)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.broker.ibkr_client import IBKRBroker
from domain.models.position import Position, PortfolioSummary


class PortfolioTools:
    """Portfolio tools for AI function calling - QS Optimized."""

    def __init__(self, broker: Optional[IBKRBroker] = None):
        """Initialize portfolio tools."""
        self._broker = broker or IBKRBroker()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_account_summary",
                    "description": "Get account summary with USD cash available for trading. Use this to verify we have enough capital for the trade.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_positions",
                    "description": "Get all current open positions. Use this to check position count and if we already have a position in the same ticker.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    def get_handlers(self) -> Dict[str, callable]:
        """Get tool handler functions."""
        return {
            "get_account_summary": self.get_account_summary,
            "get_positions": self.get_positions,
        }

    def _extract_usd_value(self, data: Dict[str, Any], key: str) -> Optional[float]:
        """Extract USD value from IBKR account data."""
        usd_key = f"{key}-s"
        if usd_key in data:
            val = data[usd_key]
            if isinstance(val, dict) and val.get("currency") == "USD":
                return float(val.get("amount", 0))

        if key in data:
            val = data[key]
            if isinstance(val, dict):
                if val.get("currency") == "USD":
                    return float(val.get("amount", 0))
                if "amount" in val:
                    return float(val.get("amount", 0))
            elif isinstance(val, (int, float)):
                return float(val)

        return None

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary focused on USD trading."""
        summary = self._broker.get_account_summary()

        if not summary:
            return {"error": "Unable to fetch account summary", "timestamp": datetime.now().isoformat()}

        usd_cash = self._extract_usd_value(summary, "totalcashvalue") or 0
        usd_buying_power = self._extract_usd_value(summary, "buyingpower") or 0
        usd_net_liq = self._extract_usd_value(summary, "netliquidation") or 0

        result = {
            "usd_available_for_trading": usd_cash,
            "usd_buying_power": usd_buying_power,
            "usd_net_liquidation": usd_net_liq,
            "currency": "USD",
            "timestamp": datetime.now().isoformat(),
        }

        if result["usd_available_for_trading"] < 500:
            result["warning"] = "Low USD balance for options trading"

        return result

    def get_positions(self) -> Dict[str, Any]:
        """Get current positions."""
        positions_data = self._broker.get_positions()
        positions = [Position.from_ibkr(p).to_dict() for p in positions_data]

        # Extract just ticker symbols for easy checking
        tickers = [p["symbol"].split()[0] for p in positions]  # Handle option symbols

        return {
            "positions": positions,
            "count": len(positions),
            "tickers": tickers,
            "timestamp": datetime.now().isoformat(),
        }

    def get_portfolio_summary(self) -> PortfolioSummary:
        """Get full portfolio summary."""
        summary = self._broker.get_account_summary() or {}
        positions_data = self._broker.get_positions()
        pnl_data = self._broker.get_pnl() or {}

        positions = [Position.from_ibkr(p) for p in positions_data]
        usd_cash = self._extract_usd_value(summary, "totalcashvalue") or 0
        usd_net_liq = self._extract_usd_value(summary, "netliquidation") or 0

        return PortfolioSummary(
            account_id=summary.get("accountId", ""),
            net_liquidation=usd_net_liq,
            total_cash=usd_cash,
            unrealized_pnl=float(pnl_data.get("unrealizedPnl", 0)),
            realized_pnl=float(pnl_data.get("realizedPnl", 0)),
            positions=positions,
        )
